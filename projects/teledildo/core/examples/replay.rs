//! Replay a TCode script through the governor on the host and print the
//! resulting setpoint timeline. Useful for sanity-checking limits before
//! flashing.
//!
//! ```text
//! cargo run --example replay -- 1 < script.tcode
//! ```
//!
//! Each input line is `<time_ms> <tcode line>`; the optional argument is the
//! tick period in milliseconds (default 10). Lines starting with `#` are
//! comments. With no input (a terminal, or an empty stream) a built-in demo
//! script runs.

#![allow(
    clippy::arithmetic_side_effects,
    clippy::indexing_slicing,
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic
)]

use std::io::{self, BufRead};

use teledildo_core::governor::{Disposition, Governor, Limits, Sensors};
use teledildo_core::tcode::parse_line;

const DEMO: &str = "\
0 D0
0 V09999
500 V09999
1000 V09999 L05000I1000
1500 V09999
2000 V09999
6000 DSTOP
6100 V05000
";

fn main() {
    let tick_ms: u64 = std::env::args()
        .nth(1)
        .and_then(|a| a.parse().ok())
        .unwrap_or(10);

    let stdin = io::stdin();
    let mut script: Vec<(u64, String)> = Vec::new();
    let mut lines: Vec<String> = if io::IsTerminal::is_terminal(&stdin) {
        Vec::new()
    } else {
        stdin.lock().lines().map_while(Result::ok).collect()
    };
    if lines
        .iter()
        .all(|l| l.trim().is_empty() || l.trim_start().starts_with('#'))
    {
        lines = DEMO.lines().map(String::from).collect();
    }
    for l in lines {
        let l = l.trim();
        if l.is_empty() || l.starts_with('#') {
            continue;
        }
        if let Some((t, rest)) = l.split_once(char::is_whitespace) {
            if let Ok(t) = t.parse() {
                script.push((t, rest.trim().to_string()));
            }
        }
    }
    script.sort_by_key(|(t, _)| *t);

    let limits = Limits::DEFAULT
        .validated()
        .unwrap_or_else(|e| panic!("bad limits: {e:?}"));
    let mut g = Governor::new(limits);
    let end = script.last().map_or(0, |(t, _)| *t) + 4000;
    let mut next = 0usize;
    let mut now = 0u64;
    println!(
        "{:>8}  {:>6} {:>6} {:>6}  {:>3}  state",
        "t_ms", "vibe0", "vibe1", "lin0", "en"
    );
    while now <= end {
        while let Some((t, line)) = script.get(next) {
            if *t > now {
                break;
            }
            for item in parse_line(line.as_bytes()) {
                match item {
                    Ok(cmd) => match g.handle(&cmd, now) {
                        Disposition::Reply(q) => {
                            println!("{now:>8}  -> reply {:?}", q.reply("replay"));
                        }
                        Disposition::Applied => {}
                        other => println!("{now:>8}  !! {other:?} for {cmd:?}"),
                    },
                    Err(e) => println!("{now:>8}  !! parse error {e:?} in {line:?}"),
                }
            }
            next += 1;
        }
        let out = g.tick(now, &Sensors::default());
        println!(
            "{now:>8}  {:>6} {:>6} {:>6}  {:>3}  {:?}",
            out.vibe[0].raw(),
            out.vibe[1].raw(),
            out.linear[0].raw(),
            u8::from(out.driver_enable),
            g.state()
        );
        now += tick_ms;
    }
}
