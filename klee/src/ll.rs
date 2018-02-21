use cty::{c_char, c_void};

#[cfg(feature = "klee_mode")]
extern "C" {
    pub fn abort() -> !;
    pub fn klee_assume(cond: bool);
    pub fn klee_make_symbolic(ptr: *mut c_void, size: usize, name: *const c_char);
}

#[cfg(not(feature = "klee_mode"))]
pub unsafe fn abort() -> ! {
    loop {}
}

#[cfg(not(feature = "klee_mode"))]
pub unsafe fn klee_assume(_cond: bool) {}

#[cfg(not(feature = "klee_mode"))]
pub unsafe fn klee_make_symbolic(_ptr: *mut c_void, _size: usize, _name: *const c_char) {}
