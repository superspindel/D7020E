#![no_std]
#![feature(compiler_builtins_lib)]
#![feature(lang_items)]

extern crate compiler_builtins;
extern crate cstr_core;
extern crate cty;

// mod lang_items;
mod ll;

use core::mem;

use cty::c_void;

#[doc(hidden)]
pub use cstr_core::CStr;

#[doc(hidden)]
#[inline]
pub fn k_symbol<T>(name: &CStr) -> T {
    let mut t: T = unsafe { mem::uninitialized() };
    unsafe {
        ll::klee_make_symbolic(
            &mut t as *mut T as *mut c_void,
            mem::size_of::<T>(),
            name.as_ptr(),
        );
    }
    t
}

#[doc(hidden)]
#[inline]
pub fn k_mk_symbol<T>(t: &mut T, name: &CStr) {
    unsafe {
        ll::klee_make_symbolic(
            t as *mut T as *mut c_void,
            mem::size_of::<T>(),
            name.as_ptr(),
        );
    }
}

#[inline(never)]
pub fn k_abort() -> ! {
    unsafe {
        ll::abort();
    }
}

/// assume a condition involving symbolic variables
#[inline(never)]
pub fn k_assume(cond: bool) {
    unsafe {
        ll::klee_assume(cond);
    }
}

/// assert a condition involving symbolic variables
#[inline(never)]
pub fn k_assert(e: bool) {
    if !e {
        k_abort();
    }
}

/// make a variable symbolic
#[macro_export]
macro_rules! k_symbol {
    ($id:ident, $name:expr) => {
        #[allow(unsafe_code)]
        $crate::k_mk_symbol(
            unsafe { &mut $id },
            unsafe { $crate::CStr::from_bytes_with_nul_unchecked(concat!($name, "\0").as_bytes()) }
        )
    }
}
