# Two hands, one passage

[Relay.obend](Relay.obend) is a small source instrument; its hand holds at most
five measures. [relay.examples](relay.examples) is its inspectable behavior
example, not a recipe hidden in a Python test. Two independent copies compose by
passing an exact typed result into the next hand. A full receiver refuses the
whole passage, and a result of the wrong semantic type also refuses after earlier
calls have run provisionally. The examples read both totals after each refusal.

The existing `examples DelveTalk 1` notation now admits named fixtures and native
transactions. `fixture peer` installs the exact proposed source into another
independent object in the disposable example world. `send peer/count` selects a
named object; an unqualified command targets `candidate`. Within `transaction`,
`call OBJECT/COMMAND` declares each call and its input. `from previous` takes the
immediately preceding checked result through native `inputFrom`; transport code
does not decode and reconstruct the result. The enclosing `as` supplies one
caller for the whole transaction. `at initial` deliberately uses initial roots;
otherwise current exact roots are captured. A case holds at most eight objects
and each transaction at most sixteen calls; the existing 64-case, 256-step and
1 MiB source bounds still apply.

The inhabitant uses the existing Writing offer to inspect installed source and
retain a variation containing both revised source and authored examples. Candidate
shows those examples beside the proposed source. Its offered check requests the
existing compiler worker, which runs disposable native worlds and retains the
exact source, examples, outcomes and report. Candidate retains the requesting
inhabitant; source policy decides readiness and adoption. Examples grant no
identity or authority in the shared world.

[The receiving journey](../../conformance/test_behavior_examples.py) exercises an
incorrect assertion, inspects its failed retained result, revises source and
examples into a fresh variation, then runs the corrected example through the
actual offered check. It confirms typed cross-object dataflow, atomic refusal,
attribution and unchanged shared target state. Independent fixture module sets
are outside this compact contract; every fixture executes the exact source under
review.
