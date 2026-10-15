# Design brief

TaxTrace is a review workspace for one fictional return, Okafor–Lindqvist, tax year 2025. The person using it is a preparer, a reviewer, or a partner. Their job is to see where a number came from and to record a decision. The return itself stays the engine's v3 output.

## The screen

The left side is the navigation. The main area is one task at a time: the computed return, the lines, the documents, the findings, filing readiness, the schedules, questions, version history, or the timeline. A line or a document opens in a drawer on the right. The amount stays at the top of that drawer while the sources, the explanation, and the review note sit underneath it.

That drawer is the trace. A wage amount lists the two W-2 fields that support it. Opening a field draws a box on a simulated page at the position stored in the packet. The packet has no page image, and the screen says so.

## Decisions a reviewer can record

A review note is separate from the return. The preparer who was assigned at the start cannot sign off their own work. A verified or blocked note names one of the firm's verification types. A tax effect over $1,000 needs the partner. Open notes, a verified note with no authority, and an unfinished Form 8867 block filing. A later note on an input clears the sign-off that used that input. Questions and proposed adjustments are stored beside the return and do not change an amount.

Social Security numbers stay masked. A staff member with clearance can open one, and that view is logged. The role switcher is a demonstration header, not a login.

## Explanations

Explain from the packet retrieves the line and the fields already attached to it. The draft is shown only when each citation and each amount is in that evidence. A question that tells the system to ignore the packet is refused. The line amount does not change.

## What the interface does not do

It does not recompute tax, edit a return number, or file a new return. Dollar effects on the findings use the packet's own rates or a named what-if result. The e-file history is a replay of the four submissions in the packet. Prior-year lines that moved by more than 10 percent and more than $1,000 are listed as explanation flags, not as corrections.
