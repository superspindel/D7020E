#![no_std]
#![feature(compiler_builtins_lib)]
#![feature(lang_items)]

extern crate compiler_builtins;
extern crate cstr_core;
extern crate cty;

// mod lang_items;
pub mod ll;

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

#[inline(always)]
pub fn k_abort() -> ! {
    unsafe {
        ll::abort();
    }
}

/// assume a condition involving symbolic variables
#[inline(always)]
pub fn k_assume(cond: bool) {
    unsafe {
        ll::klee_assume(cond);
    }
}

/// assert a condition involving symbolic variables
#[inline(always)]
pub fn k_assert(e: bool) {
    if !e {
        unsafe {
            ll::abort();
        }
    }
}

/// make a variable symbolic
#[macro_export]
macro_rules! k_symbol {
    ($id:expr, $name:expr) => {
        {
            #[allow(unsafe_code)]
            #[allow(warnings)]
            $crate::k_mk_symbol(
                unsafe { $id },
                unsafe { $crate::CStr::from_bytes_with_nul_unchecked(concat!($name, "\0").as_bytes()) }
            )
        }
    }
}

/// assertion
#[macro_export]
macro_rules! k_assert {
    ($e: expr) => {
        {
            use klee::ll;
            if !$e {
                unsafe {
                    ll::abort();
                }
            }
        }
    }
}

#[macro_export]
macro_rules! k_visit {
    ()=> {
        {
            #[allow(unsafe_code)]
            unsafe {
                core::ptr::read_volatile(&0);
            }
        }
    }
}

#[cfg(feature = "klee_mode")]
pub fn k_read<T>(p: &T) {
    unsafe { core::ptr::read_volatile(p) };
}

#[cfg(not(feature = "klee_mode"))]
pub fn k_read<T>(_p: &T) {}
