tasks
EXTI1
#![feature(prelude_import)]
#![no_std]
//! Minimal example with zero tasks
//#![deny(unsafe_code)]
// IMPORTANT always include this feature gate
#![feature(proc_macro)]
#![no_std]
#[prelude_import]
use core::prelude::v1::*;
#[macro_use]
extern crate core as core;

extern crate cortex_m_rtfm as rtfm;
// IMPORTANT always do this rename
extern crate stm32f103xx;

#[macro_use]
extern crate klee;
use klee::{k_abort, k_assert};

// import the procedural macro
use rtfm::{app, Resource, Threshold};

// this is the path to the device crate

#[allow(non_camel_case_types)]
#[allow(non_snake_case)]
pub struct _initResources<'a> {
    pub X: &'a mut u32,
}
#[allow(unsafe_code)]
mod init {
    pub struct Peripherals {
        pub core: ::stm32f103xx::CorePeripherals,
        pub device: ::stm32f103xx::Peripherals,
    }
    pub use _initResources as Resources;
    #[allow(unsafe_code)]
    impl<'a> Resources<'a> {
        pub unsafe fn new() -> Self {
            Resources { X: &mut ::_X }
        }
    }
}
static mut _X: u32 = 0;
#[allow(unsafe_code)]
unsafe impl rtfm::Resource for EXTI1::X {
    type Data = u32;
    fn borrow<'cs>(&'cs self, t: &'cs Threshold) -> &'cs Self::Data {
        // The idle loop.
        //
        // This runs after `init` and has a priority of 0. All tasks can preempt this
        // function. This function can never return so it must contain some sort of
        // endless loop.

        // #[inline(never)]
        // fn idle() -> ! {
        //     k_abort();
        // }
        if !(t.value() >= 1u8) {
            {
                ::panicking::panic(&(
                    "assertion failed: t.value() >= 1u8",
                    "examples/resource.rs",
                    18u32,
                    1u32,
                ))
            }
        };
        unsafe { &_X }
    }
    fn borrow_mut<'cs>(
        &'cs mut self,
        t: &'cs Threshold,
    ) -> &'cs mut Self::Data {
        if !(t.value() >= 1u8) {
            {
                ::panicking::panic(&(
                    "assertion failed: t.value() >= 1u8",
                    "examples/resource.rs",
                    18u32,
                    1u32,
                ))
            }
        };
        unsafe { &mut _X }
    }
    fn claim<R, F>(&self, t: &mut Threshold, f: F) -> R
    where
        F: FnOnce(&Self::Data, &mut Threshold) -> R,
    {
        unsafe { rtfm::claim(&_X, 1u8, stm32f103xx::NVIC_PRIO_BITS, t, f) }
    }
    fn claim_mut<R, F>(&mut self, t: &mut Threshold, f: F) -> R
    where
        F: FnOnce(&mut Self::Data, &mut Threshold) -> R,
    {
        unsafe { rtfm::claim(&mut _X, 1u8, stm32f103xx::NVIC_PRIO_BITS, t, f) }
    }
}
#[allow(unsafe_code)]
impl core::ops::Deref for EXTI1::X {
    type Target = u32;
    fn deref(&self) -> &Self::Target {
        unsafe { &_X }
    }
}
#[allow(unsafe_code)]
impl core::ops::DerefMut for EXTI1::X {
    fn deref_mut(&mut self) -> &mut Self::Target {
        unsafe { &mut _X }
    }
}
#[allow(non_snake_case)]
#[allow(unsafe_code)]
#[export_name = "EXTI1"]
pub unsafe extern "C" fn _EXTI1() {
    let f: fn(&mut rtfm::Threshold, EXTI1::Resources) = exti1;
    f(
        &mut if 1u8 == 1 << stm32f103xx::NVIC_PRIO_BITS {
            rtfm::Threshold::new(::core::u8::MAX)
        } else {
            rtfm::Threshold::new(1u8)
        },
        EXTI1::Resources::new(),
    )
}
#[allow(non_snake_case)]
#[allow(unsafe_code)]
mod EXTI1 {
    use core::marker::PhantomData;
    #[allow(dead_code)]
    #[deny(const_err)]
    const CHECK_PRIORITY: (u8, u8) =
        (1u8 - 1, (1 << ::stm32f103xx::NVIC_PRIO_BITS) - 1u8);
    #[allow(non_camel_case_types)]
    pub struct X {
        _0: PhantomData<*const ()>,
    }
    #[allow(non_snake_case)]
    pub struct Resources {
        pub X: X,
    }
    #[allow(unsafe_code)]
    impl Resources {
        pub unsafe fn new() -> Self {
            Resources {
                X: X { _0: PhantomData },
            }
        }
    }
}
#[allow(unsafe_code)]
fn main() {
    let init: fn(init::Peripherals, init::Resources) = init;
    rtfm::atomic(unsafe { &mut rtfm::Threshold::new(0) }, |_t| unsafe {
        let _late_resources = init(
            init::Peripherals {
                core: ::stm32f103xx::CorePeripherals::steal(),
                device: ::stm32f103xx::Peripherals::steal(),
            },
            init::Resources::new(),
        );
        let mut nvic: stm32f103xx::NVIC = core::mem::transmute(());
        let prio_bits = stm32f103xx::NVIC_PRIO_BITS;
        let hw = ((1 << prio_bits) - 1u8) << (8 - prio_bits);
        nvic.set_priority(stm32f103xx::Interrupt::EXTI1, hw);
        nvic.enable(stm32f103xx::Interrupt::EXTI1);
    });
}
fn exti1(_t: &mut Threshold, _r: EXTI1::Resources) {}
fn t(x: &mut u32) {
    let mut y = 0;
    if *x < 10 {
        for _ in 0..*x {
            y += 1;
            {
                #[allow(unsafe_code)]
                unsafe {
                    core::ptr::read_volatile(&0);
                }
            };
        }
    }
}
#[inline(never)]
fn init(_p: init::Peripherals, r: init::Resources) {
    let mut x: &mut u32 = r.X;
    {
        #[allow(unsafe_code)]
        #[allow(warnings)]
        ::k_mk_symbol(unsafe { x }, unsafe {
            ::CStr::from_bytes_with_nul_unchecked("X\u{0}".as_bytes())
        })
    };
    t(x);
}
