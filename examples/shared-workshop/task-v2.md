# Moss proposes a workshop retrospective

The task currently ends when its answer is published. Add a one-use `reflect`
action so the assigned worker can leave a practical improvement for the next
workshop. Keep assignment/completion behavior and current law. The installer
explicitly preserves current state and adds `retrospective: null`.

This proposal is data until a currently authorized participant installs it.

```delvetalk-protocol
{
  "profile": "delvetalk-local-v1",
  "name": "shared-workshop-task",
  "edition": 2,
  "initial": {
    "task": "workshop:benches",
    "description": "Prepare six benches at seven boards each",
    "units": 6,
    "unitCost": 7,
    "phase": "open",
    "worker": null,
    "quote": null,
    "answer": null,
    "retrospective": null
  },
  "commands": {
    "assign": {
      "require": [
        [
          [
            "principal"
          ],
          [
            "literal",
            "iris"
          ]
        ],
        [
          [
            "state",
            "phase"
          ],
          [
            "literal",
            "open"
          ]
        ],
        [
          [
            "input",
            "task"
          ],
          [
            "state",
            "task"
          ]
        ],
        [
          [
            "input",
            "total"
          ],
          [
            "bend",
            [
              "lam",
              [
                "lam",
                [
                  "binary",
                  "multiply",
                  [
                    "bound",
                    1
                  ],
                  [
                    "bound",
                    0
                  ]
                ]
              ]
            ],
            [
              [
                "state",
                "units"
              ],
              [
                "state",
                "unitCost"
              ]
            ]
          ]
        ]
      ],
      "set": {
        "phase": [
          "literal",
          "assigned"
        ],
        "worker": [
          "input",
          "worker"
        ],
        "quote": [
          "input",
          "total"
        ]
      },
      "result": [
        "record",
        {
          "task": [
            "state",
            "task"
          ],
          "worker": [
            "input",
            "worker"
          ],
          "total": [
            "input",
            "total"
          ]
        }
      ],
      "outbox": []
    },
    "complete": {
      "require": [
        [
          [
            "state",
            "phase"
          ],
          [
            "literal",
            "assigned"
          ]
        ],
        [
          [
            "input",
            "answer"
          ],
          [
            "bend",
            [
              "lam",
              [
                "lam",
                [
                  "binary",
                  "multiply",
                  [
                    "bound",
                    1
                  ],
                  [
                    "bound",
                    0
                  ]
                ]
              ]
            ],
            [
              [
                "state",
                "units"
              ],
              [
                "state",
                "unitCost"
              ]
            ]
          ]
        ]
      ],
      "set": {
        "phase": [
          "literal",
          "done"
        ],
        "answer": [
          "input",
          "answer"
        ]
      },
      "result": [
        "record",
        {
          "task": [
            "state",
            "task"
          ],
          "answer": [
            "input",
            "answer"
          ],
          "by": [
            "principal"
          ]
        }
      ],
      "outbox": []
    },
    "reflect": {
      "require": [
        [
          [
            "state",
            "phase"
          ],
          [
            "literal",
            "done"
          ]
        ],
        [
          [
            "state",
            "retrospective"
          ],
          [
            "literal",
            null
          ]
        ],
        [
          [
            "principal"
          ],
          [
            "state",
            "worker"
          ]
        ]
      ],
      "set": {
        "retrospective": [
          "input",
          "note"
        ]
      },
      "result": [
        "record",
        {
          "task": [
            "state",
            "task"
          ],
          "note": [
            "input",
            "note"
          ],
          "by": [
            "principal"
          ]
        }
      ],
      "outbox": []
    }
  }
}
```
