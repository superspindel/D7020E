//! Minimal example with zero tasks
//#![deny(unsafe_code)]
// IMPORTANT always include this feature gate
#![feature(proc_macro)]
#![no_std]

extern crate cortex_m_rtfm as rtfm;
// IMPORTANT always do this rename
extern crate stm32f103xx;

#[macro_use]
extern crate klee;
use klee::{k_abort, k_read};

// import the procedural macro
use rtfm::{app, Resource, Threshold};

app! {
    // this is the path to the device crate
    device: stm32f103xx,

    resources: {
        static X:u32 = 0;
        static Y:u32 = 0;
    },

    tasks: {
        EXTI1: {
            path: exti1,
            resources: [X],
        },

        EXTI2: {
            path: exti2,
            resources: [X, Y],
        },
    },
}

fn exti1(t: &mut Threshold, r: EXTI1::Resources) {
    let mut y = 0;
    r.X.claim(t, |x, _| {
        if *x < 10 {
            for _ in 0..*x {
                y += 1;
                k_visit!();
            }
        }
    });
    k_read(&y);
}

fn exti2(_t: &mut Threshold, _r: EXTI2::Resources) {}

#[inline(never)]
fn init(_p: init::Peripherals, _r: init::Resources) {}

// The idle loop.
//
// This runs after `init` and has a priority of 0. All tasks can preempt this
// function. This function can never return so it must contain some sort of
// endless loop.

#[inline(never)]
fn idle() -> ! {
    k_abort()
}
