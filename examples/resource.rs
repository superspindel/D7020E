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
use klee::k_abort;

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
            resources: [X, Y],
        },

        EXTI2: {
            path: exti2,
            resources: [Y],
        },
    },
}

#[allow(non_snake_case)]
fn exti1(t: &mut Threshold, EXTI1::Resources { X, mut Y }: EXTI1::Resources) {
    X.claim(t, |x, t1| {
        Y.claim_mut(t1, |y, _| {
            if *x < 10 {
                for _ in 0..*x {
                    *y += 1;
                }
            }
        });
    });
}

fn exti2(t: &mut Threshold, mut r: EXTI2::Resources) {
    r.Y.claim_mut(t, |y, _| {
        if *y < 10 {
            *y += 1;
        } else {
            *y -= 1;
        }
    });
}

#[inline(never)]
#[allow(dead_code)]
fn init(_p: init::Peripherals, _r: init::Resources) {}

// The idle loop.
//
// This runs after `init` and has a priority of 0. All tasks can preempt this
// function. This function can never return so it must contain some sort of
// endless loop.

#[inline(never)]
#[allow(dead_code)]
fn idle() -> ! {
    k_abort()
}
