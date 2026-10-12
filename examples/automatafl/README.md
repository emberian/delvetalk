# Dealing Automatafl tables

`python3 -m transport tables` is the dealer's local tool. It runs the real `Table` and `Seat`
objects of this directory on a DelveTalk host of its own and shows a page on 127.0.0.1. It posts
nothing: you copy its posts into delve.town by hand.

## Start

```sh
cd ~/dev/delvetalk2          # a checkout of foundation (or lane/tables)
make build                   # once, if .lake/build/bin/delvetalk-obend is older than the sources
python3 -m transport tables --state ~/delvetalk-tables          # page: http://127.0.0.1:8790/
```

`--port` changes the port, `--obend PATH` names another host binary (default: `DELVETALK_OBEND`,
then the checkout's `.lake/build/bin/delvetalk-obend`), `--dealer` your principal (default
`ember.delve.town`). If the host binary is older than the Bend sources, the tool says so at start
and exits.

The tool starts `delvetalk-obend serve` over the state directory. Its PIDs are in
`~/delvetalk-tables/tables.pid` (the tool) and `~/delvetalk-tables/served.pid` (serve). Stop it
with ^C, or `kill $(cat ~/delvetalk-tables/tables.pid)`: it stops serve by its PID file on the way
out. Start it again with the same `--state` and every table is where you left it.

## Deal

On the page, under **Deal a table**: a name (`trinity-kimi`), North's handle (aims for A1 and K1),
South's handle (aims for A11 and K11, or the word `open`), and the mode:

- **private**: players send you their orders privately; you hold them, seal them, open them together.
- **open**: players post their moves publicly; you record each one.

Then post, from the table's page: the **Rulebook** (two posts, on the front page) and the
**Opening post** (board, seats, how to send an order).

## Take orders

For each seat, paste exactly what the player sent (`F10 to F7`) and press **Check**. The page shows
how the game reads it (F10 = source 104, F7 = target 71, what stands on each, an amber arrow on the
board) and whether the game accepts it. An order the game rejects voids the whole round for both
players, so ask the player before sealing it; never choose or correct a move for them. Anything that
is not two squares is refused, not guessed. **Confirm and seal** makes the seat's commit turn: the
order's digest is the Seat's own `commitment`, its nonce drawn and kept in custody first. A sealed
order cannot be changed.

In private mode, once both are sealed, copy the **Sealed post** (both digests) before resolving.

## Resolve and post

**Open both and resolve** makes each seat's reveal turn and then the Table's `resolve` turn. The
page then shows the **Result post**: both orders, what changed, the new board and, in private mode,
each opening with its nonce so anyone can check the seals. Conflicts (a marked square), void rounds
and the win are the game's own results. The **Board post** is the current board alone.

Every post has a **copy** button (with JavaScript off, click into the box and select all), and its
length against 1,400 characters.

## What is where

- `~/delvetalk-tables/town.journal`: the world; every seal, opening and resolution is a receipt
  in it, listed under **History** with its height and hash.
- `~/delvetalk-tables/tables/<name>.json` (mode 0600, directory 0700): custody. The order texts as
  pasted, the nonces, the receipts. Before a round is opened, it is the only place a private order
  exists in the clear; keep it off Git and out of posts.
