//! Minimal example with zero tasks
//#![deny(unsafe_code)]
// IMPORTANT always include this feature gate
#![feature(proc_macro)]
#![feature(used)]
#![no_std]

extern crate cortex_m_rtfm as rtfm;
// IMPORTANT always do this rename
extern crate stm32f413;

#[macro_use]
extern crate klee;
use klee::{k_abort, k_assert, k_assume};

// import the procedural macro
use rtfm::{app, Resource, Threshold};

app! {
    // this is the path to the device crate
    device: stm32f413,

    resources: {
        static X:u64 = 1;
        static A:[u64; 11] = [0; 11];
        static I:u64 = 0;
    },

    tasks: {
        EXTI1: {
            path: exti1,
            priority: 1,
            resources: [X],
        },
        EXTI2: {
            path: exti2,
            priority: 1,
            resources: [X, A, I],
        },
    },
}

fn exti1(t: &mut Threshold, mut r: EXTI1::Resources) {
    // k_assume(*r.X > _ && *r.X < _); // pre-condition on X
    let u = 11 / (*r.X);
    *r.X = u;
    // k_assert(*r.X > _ && *r.X < _); // post-condition on X
}

fn exti2(t: &mut Threshold, r: EXTI2::Resources) {
    // k_assume(*r.X > _ && *r.X < _); // pre-condition on X
    let b = r.A[*r.X as usize];
    *r.I = b;
    // as we don't change X post-condition is trivially true
}

// The `init` function
//
// This function runs as an atomic section before any tasks
// are allowed to start
#[inline(never)]
#[allow(dead_code)]
fn init(_p: init::Peripherals) {}

// The idle loop.
//
// This runs after `init` and has a priority of 0. All tasks can preempt this
// function. This function can never return so it must contain some sort of
// endless loop.
#[inline(never)]
fn idle() -> ! {
    loop {}
}

// Assignments
//
// Rust strives at being a safe language.
// - Memory safety,
//   - static checking where possible
//   - run-time checking causing `panic!` on violation
//
// - No undefined behavior in "safe" Rust
//   - panic! in case undef behavior (e.g., div 0)
//
// Compiling and analysing the code using KLEE
//
// What problem(s) did KLEE identify
// ** your answer here **
//
// Now try to solve this by contracts
// You should not change the code, just enable the contacts
// The `_` should be filled with concrete values
//
// Can you find a type invariant that satisfies BOTH pre- and post-conditions
// at the same time.
//
// If not, why is that not possible?
