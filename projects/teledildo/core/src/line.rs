//! Fixed-capacity line assembler.
//!
//! Serial transports deliver TCode in arbitrary chunks. [`LineBuffer`]
//! accumulates bytes until a `\n` and exposes the completed line as a slice.
//! Lines longer than the capacity are discarded whole (never truncated into a
//! different, possibly valid, command) and counted in
//! [`LineBuffer::dropped_lines`].

/// Result of pushing one byte into a [`LineBuffer`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Push {
    /// Byte stored; line not yet complete.
    Pending,
    /// A newline arrived: [`LineBuffer::line`] now holds a complete line.
    Complete,
    /// The line exceeded capacity and is being discarded up to the next `\n`.
    Overflow,
}

/// Accumulates bytes into newline-terminated lines with a fixed `N`-byte
/// capacity and no allocation.
#[derive(Clone, Debug)]
pub struct LineBuffer<const N: usize> {
    buf: [u8; N],
    len: usize,
    ready: bool,
    discarding: bool,
    dropped: u32,
}

impl<const N: usize> Default for LineBuffer<N> {
    fn default() -> Self {
        Self::new()
    }
}

impl<const N: usize> LineBuffer<N> {
    /// An empty buffer.
    #[must_use]
    pub const fn new() -> Self {
        Self {
            buf: [0; N],
            len: 0,
            ready: false,
            discarding: false,
            dropped: 0,
        }
    }

    /// Push one byte. When this returns [`Push::Complete`], read the line with
    /// [`Self::line`]; the next `push` automatically starts a fresh line.
    pub fn push(&mut self, byte: u8) -> Push {
        if self.ready {
            self.clear();
        }
        if self.discarding {
            if byte == b'\n' {
                self.discarding = false;
                self.dropped = self.dropped.saturating_add(1);
            }
            return Push::Overflow;
        }
        if byte == b'\n' {
            self.ready = true;
            return Push::Complete;
        }
        if let Some(slot) = self.buf.get_mut(self.len) {
            *slot = byte;
            self.len = self.len.saturating_add(1);
            Push::Pending
        } else {
            self.len = 0;
            self.discarding = true;
            Push::Overflow
        }
    }

    /// Push a chunk, invoking `on_line` for each completed line.
    pub fn push_all(&mut self, bytes: &[u8], mut on_line: impl FnMut(&[u8])) {
        for &b in bytes {
            if self.push(b) == Push::Complete {
                on_line(self.line());
            }
        }
    }

    /// The bytes of the current (possibly incomplete) line, without `\n`.
    #[must_use]
    pub fn line(&self) -> &[u8] {
        self.buf.get(..self.len).unwrap_or(&[])
    }

    /// Whether a complete line is waiting to be read.
    #[must_use]
    pub const fn is_ready(&self) -> bool {
        self.ready
    }

    /// Discard the current line.
    pub fn clear(&mut self) {
        self.len = 0;
        self.ready = false;
    }

    /// Number of over-length lines discarded so far.
    #[must_use]
    pub const fn dropped_lines(&self) -> u32 {
        self.dropped
    }
}

#[cfg(test)]
#[allow(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::indexing_slicing,
    clippy::arithmetic_side_effects,
    clippy::unreachable,
    clippy::panic
)]
mod tests {
    use super::*;
    use std::vec;
    use std::vec::Vec;

    #[test]
    fn assembles_lines_across_chunks() {
        let mut lb = LineBuffer::<16>::new();
        let mut lines: Vec<Vec<u8>> = Vec::new();
        lb.push_all(b"L05", |_| unreachable!());
        lb.push_all(b"00\nV0999", |l| lines.push(l.to_vec()));
        lb.push_all(b"9\n\n", |l| lines.push(l.to_vec()));
        assert_eq!(
            lines,
            vec![b"L0500".to_vec(), b"V09999".to_vec(), Vec::new()]
        );
        assert_eq!(lb.dropped_lines(), 0);
    }

    #[test]
    fn overflow_discards_whole_line_and_recovers() {
        let mut lb = LineBuffer::<4>::new();
        let mut lines: Vec<Vec<u8>> = Vec::new();
        lb.push_all(b"L0500I100\nD0\n", |l| lines.push(l.to_vec()));
        assert_eq!(lines, vec![b"D0".to_vec()]);
        assert_eq!(lb.dropped_lines(), 1);
        // Exactly N bytes then newline fits.
        lines.clear();
        lb.push_all(b"ABCD\n", |l| lines.push(l.to_vec()));
        assert_eq!(lines, vec![b"ABCD".to_vec()]);
    }

    #[test]
    fn ready_line_is_replaced_on_next_push() {
        let mut lb = LineBuffer::<8>::new();
        assert_eq!(lb.push(b'A'), Push::Pending);
        assert_eq!(lb.push(b'\n'), Push::Complete);
        assert!(lb.is_ready());
        assert_eq!(lb.line(), b"A");
        assert_eq!(lb.push(b'B'), Push::Pending);
        assert!(!lb.is_ready());
        assert_eq!(lb.line(), b"B");
    }
}
