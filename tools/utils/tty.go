package utils

import (
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"os"
	"syscall"
	"time"

	"golang.org/x/sys/unix"
)

const (
	TCSANOW   = 0
	TCSADRAIN = 1
	TCSAFLUSH = 2
)

type Term struct {
	name   string
	fd     int
	states []unix.Termios
}

func eintr_retry_noret(f func() error) error {
	for {
		qerr := f()
		if qerr == unix.EINTR {
			continue
		}
		return qerr
	}
}

func eintr_retry_intret(f func() (int, error)) (int, error) {
	for {
		q, qerr := f()
		if qerr == unix.EINTR {
			continue
		}
		return q, qerr
	}
}

type TermiosOperation func(t *unix.Termios)

func get_vmin_and_vtime(d time.Duration) (uint8, uint8) {
	if d > 0 {
		// VTIME is expressed in terms of deciseconds
		vtimeDeci := d.Milliseconds() / 100
		// ensure valid range
		vtime := uint8(clamp(vtimeDeci, 1, 0xff))
		return 0, vtime
	}
	// block indefinitely until we receive at least 1 byte
	return 1, 0
}

func SetReadTimeout(d time.Duration) TermiosOperation {
	vmin, vtime := get_vmin_and_vtime(d)
	return func(t *unix.Termios) {
		t.Cc[unix.VMIN] = vmin
		t.Cc[unix.VTIME] = vtime
	}
}

var SetBlockingRead TermiosOperation = SetReadTimeout(0)

var SetRaw TermiosOperation = func(t *unix.Termios) {
	// This attempts to replicate the behaviour documented for cfmakeraw in
	// the termios(3) manpage, as Go doesnt wrap cfmakeraw probably because its not in POSIX
	t.Iflag &^= unix.IGNBRK | unix.BRKINT | unix.PARMRK | unix.ISTRIP | unix.INLCR | unix.IGNCR | unix.ICRNL | unix.IXON
	t.Oflag &^= unix.OPOST
	t.Lflag &^= unix.ECHO | unix.ECHONL | unix.ICANON | unix.ISIG | unix.IEXTEN
	t.Cflag &^= unix.CSIZE | unix.PARENB
	t.Cflag |= unix.CS8
	t.Cc[unix.VMIN] = 1
	t.Cc[unix.VTIME] = 0
}
var SetNoEcho TermiosOperation = func(t *unix.Termios) {
	t.Lflag &^= unix.ECHO
}

func OpenTerm(name string, operations ...TermiosOperation) (self *Term, err error) {
	fd, err := eintr_retry_intret(func() (int, error) {
		return unix.Open(name, unix.O_NOCTTY|unix.O_CLOEXEC|unix.O_NDELAY|unix.O_RDWR, 0666)
	})
	if err != nil {
		return nil, &os.PathError{Op: "open", Path: name, Err: err}
	}

	self = &Term{name: name, fd: fd}
	err = eintr_retry_noret(func() error { return unix.SetNonblock(self.fd, false) })
	if err == nil {
		err = self.ApplyOperations(TCSANOW, operations...)
	}
	if err != nil {
		self.Close()
		self = nil
	}
	return
}

func OpenControllingTerm(operations ...TermiosOperation) (self *Term, err error) {
	return OpenTerm("/dev/tty", operations...) // go doesnt have a wrapper for ctermid()
}

func (self *Term) Fd() int { return self.fd }

func (self *Term) Close() error {
	err := eintr_retry_noret(func() error { return unix.Close(self.fd) })
	self.fd = -1
	return err
}

func (self *Term) Tcgetattr(ans *unix.Termios) error {
	return eintr_retry_noret(func() error { return Tcgetattr(self.fd, ans) })
}

func (self *Term) Tcsetattr(when uintptr, ans *unix.Termios) error {
	return eintr_retry_noret(func() error { return Tcsetattr(self.fd, when, ans) })
}

func (self *Term) set_termios_attrs(when uintptr, modify func(*unix.Termios)) (err error) {
	var state unix.Termios
	if err = self.Tcgetattr(&state); err != nil {
		return
	}
	new_state := state
	modify(&new_state)
	if err = self.Tcsetattr(when, &new_state); err == nil {
		self.states = append(self.states, state)
	}
	return
}

func (self *Term) ApplyOperations(when uintptr, operations ...TermiosOperation) (err error) {
	return self.set_termios_attrs(when, func(t *unix.Termios) {
		for _, op := range operations {
			op(t)
		}
	})
}

func (self *Term) PopStateWhen(when uintptr) (err error) {
	if len(self.states) == 0 {
		return nil
	}
	idx := len(self.states) - 1
	if err = self.Tcsetattr(when, &self.states[idx]); err == nil {
		self.states = self.states[:idx]
	}
	return
}

func (self *Term) PopState() error {
	return self.PopStateWhen(TCSAFLUSH)
}

func (self *Term) RestoreWhen(when uintptr) (err error) {
	if len(self.states) == 0 {
		return nil
	}
	self.states = self.states[:1]
	return self.PopStateWhen(when)
}

func (self *Term) Restore() error {
	return self.RestoreWhen(TCSAFLUSH)
}

func clamp(v, lo, hi int64) int64 {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func (self *Term) ReadWithTimeout(b []byte, d time.Duration) (n int, err error) {
	var read, write, in_err unix.FdSet
	pselect := func() (int, error) {
		read.Zero()
		write.Zero()
		in_err.Zero()
		read.Set(self.fd)
		return Select(self.fd+1, &read, &write, &in_err, d)
	}
	num_ready, err := pselect()
	if err != nil {
		return
	}
	if num_ready == 0 {
		err = os.ErrDeadlineExceeded
		return
	}
	return self.Read(b)
}

func (self *Term) Read(b []byte) (int, error) {
	n, e := eintr_retry_intret(func() (int, error) { return unix.Read(self.fd, b) })
	if n < 0 {
		n = 0
	}
	if n == 0 && len(b) > 0 && e == nil {
		return 0, io.EOF
	}
	if e != nil {
		return n, &os.PathError{Op: "read", Path: self.name, Err: e}
	}
	return n, nil
}

func (self *Term) Write(b []byte) (int, error) {
	n, e := eintr_retry_intret(func() (int, error) { return unix.Write(self.fd, b) })
	if n < 0 {
		n = 0
	}
	if n != len(b) {
		return n, io.ErrShortWrite
	}
	if e != nil {
		return n, &os.PathError{Op: "write", Path: self.name, Err: e}
	}
	return n, nil
}

func NsecToTimespec(d time.Duration) unix.Timespec {
	nv := syscall.NsecToTimespec(int64(d))
	return unix.Timespec{Sec: nv.Sec, Nsec: nv.Nsec}
}

func NsecToTimeval(d time.Duration) unix.Timeval {
	nv := syscall.NsecToTimeval(int64(d))
	return unix.Timeval{Sec: nv.Sec, Usec: nv.Usec}
}

func (self *Term) DebugPrintln(a ...interface{}) {
	msg := []byte(fmt.Sprintln(a...))
	for i := 0; i < len(msg); i += 256 {
		end := i + 256
		if end > len(msg) {
			end = len(msg)
		}
		chunk := msg[i:end]
		encoded := make([]byte, base64.StdEncoding.EncodedLen(len(chunk)))
		base64.StdEncoding.Encode(encoded, chunk)
		self.Write([]byte("\x1bP@kitty-print|"))
		self.Write(encoded)
		self.Write([]byte("\x1b\\"))
	}
}

func (self *Term) WriteAllWithTimeout(b []byte, d time.Duration) (n int, err error) {
	var read, write, in_err unix.FdSet
	var num_ready int
	n = len(b)
	pselect := func() (int, error) {
		write.Zero()
		read.Zero()
		in_err.Zero()
		write.Set(self.fd)
		return Select(self.fd+1, &read, &write, &in_err, d)
	}
	for {
		if len(b) == 0 {
			return
		}
		read.Zero()
		in_err.Zero()
		num_ready, err = pselect()
		if err != nil {
			n -= len(b)
			return
		}
		if num_ready == 0 {
			err = os.ErrDeadlineExceeded
			n -= len(b)
			return
		}
		num_written, werr := self.Write(b)
		if werr == nil {
			n -= len(b)
			return
		}
		if errors.Is(werr, io.ErrShortWrite) {
			b = b[num_written:]
			continue
		}
		err = werr
		n -= len(b)
		return
	}
}

func (self *Term) WriteFromReader(r Reader, read_timeout time.Duration, write_timeout time.Duration) (n int, err error) {
	buf := r.GetBuf()
	var rn, wn int
	var rerr error
	for {
		if len(buf) == 0 {
			rn, rerr = r.ReadWithTimeout(buf, read_timeout)
			if rerr != nil && !errors.Is(rerr, io.EOF) {
				err = rerr
				return
			}
			if rn == 0 {
				return n, nil
			}
		}
		wn, err = self.WriteAllWithTimeout(buf, write_timeout)
		n += wn
		if err != nil {
			return
		}
		buf = buf[:0]
	}
}

func (self *Term) GetSize() (*unix.Winsize, error) {
	for {
		sz, err := unix.IoctlGetWinsize(self.fd, unix.TIOCGWINSZ)
		if err != unix.EINTR {
			return sz, err
		}
	}
}
