## Purpose

Arm Q ("trích rồi đáp") is a reading arm. It asks the model to copy the part of the passage that answers the question, then to give the shortest phrase that answers what is asked. Q is the third arm of the LLM router's menu, with B and S. MC-97 runs it twice on the reading items of the wide phase, so the router can be designed from two draws of every menu arm.

## ADDED Requirements

### Requirement: Arm Q prompt
The Q prompt SHALL be the head registered in the LLM-router protocol, followed by:

- the passage of the item's frozen main-v1 reading prompt;
- the question label `\n\nCâu hỏi: `;
- the question;
- a final newline.

This is the layout of the S reading prompt. No Q prompt SHALL carry the gold answer. A Q prompt for a multiple-choice item SHALL be refused, and the campaign's prompt builder SHALL refuse arm Q.

#### Scenario: Reading item
- **WHEN** a Q prompt is built for a reading item
- **THEN** it equals the head, the item's passage, `\n\nCâu hỏi: `, the item's question and a newline

### Requirement: Scoring of arm Q
Q SHALL be scored like S on reading:

- the frozen V1 reading scorer reads the text after the last final-answer label;
- the row records `scoring_source` `raw_last_label`;
- the row carries S's format flags: whether a label is present, and whether the final line has markdown.

A replicate id MAY carry arm Q. The campaign protocol's arms, and the prompts and scoring of B, S, O, K and KS, SHALL stay unchanged.

#### Scenario: Quoted line and final answer
- **WHEN** a Q response has a `Trích dẫn:` line followed by a final `Trả lời:` line
- **THEN** the item is scored on the text after `Trả lời:` only

### Requirement: Menu design set
The menu set SHALL hold every wide-phase item of ViBidLQA test, Vi-DROP and Vi-SQuAD: the B-r1 rows of the frozen wide manifest, in manifest order, 591 + 188 + 188 = 967 items. Each item SHALL have two Q draws, 1,934 attempts in all.

Each item's frozen main-v1 reading prompt SHALL hash to its MC-90 B prompt.

The LLM-router protocol SHALL inherit the model, transport, scoring and budget blocks from the campaign protocol and SHALL copy none of them. The manifest SHALL record the SHA-256 of the campaign protocol and of the wide manifest.

#### Scenario: Prompt drift
- **WHEN** an item's frozen reading prompt no longer hashes to its MC-90 B prompt
- **THEN** building the menu manifest fails

### Requirement: Menu run gates
Execution SHALL require all of the following:

- the registered card heading and detail card;
- the registered SHA-256 of the LLM-router protocol, the campaign protocol, the wide manifest and the menu manifest;
- the campaign's endpoint and model.

The registered limits of 4 requests in flight and a breaker after 4 network failures SHALL apply, and other values SHALL be refused. Without `--execute`, the runner SHALL send no request.

#### Scenario: Changed manifest
- **WHEN** the menu manifest differs from its registered SHA-256
- **THEN** execution is refused before any request
