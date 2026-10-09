use automatafl::*;
use std::io::{self, BufRead};
fn main() {
 let mut board = Board::stock_two_player();
 for line in io::stdin().lock().lines() {
  let nums: Vec<usize> = line.unwrap().split_whitespace().map(|s| s.parse().unwrap()).collect();
  // Each request is a revealed pair, using the retained board from the previous result.
  // Original Game never clears pending_moves after a completed round; use fresh input slots.
  let mut game = Game::new(board.clone(), 2, true);
  for (y,p) in [(0,0),(10,1)] { for x in [0,10] {game.goals.push((Coord{x,y},Pid(p)));} }
  let mut accepted = true;
  for seat in 0..2 {
   let s=nums[seat*2];let t=nums[seat*2+1];
   let (feedback,_) = game.propose_move(Move{who:Pid(seat as u8),from:Coord{x:(s%11) as u8,y:(s/11) as u8},to:Coord{x:(t%11) as u8,y:(t/11) as u8}});
   accepted &= feedback == MoveFeedback::Committed;
  }
  let status = if !accepted {2} else if game.try_complete_round().is_ok() {0} else {1};
  if accepted {board=game.board.clone();}
  let cells: Vec<String> = (0..121).map(|i|match board.particles[Coord{x:(i%11) as u8,y:(i/11) as u8}.ix()].what {Particle::Vacuum=>"0",Particle::Attractor=>"1",Particle::Repulsor=>"2",Particle::Automaton=>"3"}.to_string()).collect();
  let marks:Vec<String>=(0..121).filter(|i|board.particles[Coord{x:(i%11) as u8,y:(i/11) as u8}.ix()].conflict).map(|i|i.to_string()).collect();
  println!("{{\"cells\":[{}],\"automaton\":{},\"marks\":[{}],\"status\":{},\"winner\":{}}}",cells.join(","),board.automaton_location.y as usize*11+board.automaton_location.x as usize,marks.join(","),status,game.winner.map(|p|p.0+1).unwrap_or(0));
 }
}
