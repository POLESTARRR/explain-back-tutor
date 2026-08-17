# Sample Notes

Three ready-made concepts to test the bot with before you load your own notes.
Try `python src/load_notes.py sample_notes.md`, then in Telegram send `inflation`.

## Inflation

Inflation is a sustained increase in the general price level of goods and
services in an economy over time. When inflation rises, each unit of currency
buys fewer goods and services — purchasing power falls. It's typically
measured by tracking a basket of goods over time, such as the Consumer Price
Index (CPI). Moderate, predictable inflation (roughly 2% a year in many
developed economies) is generally considered healthy because it encourages
spending and investment over hoarding cash. Central banks (like the Federal
Reserve or RBI) try to control inflation primarily through interest rates:
raising rates makes borrowing more expensive, which cools spending and slows
price growth; cutting rates does the opposite. Inflation is different from a
single price increase — it specifically means a broad, sustained rise across
the economy, not just one product getting more expensive. Hyperinflation is
an extreme, out-of-control case, often above 50% a month, usually caused by a
government printing money far faster than the economy's actual output grows.

## Photosynthesis

Photosynthesis is the process plants, algae, and some bacteria use to convert
light energy into chemical energy stored in glucose. The overall reaction
takes in carbon dioxide and water, and — using energy captured from sunlight
by chlorophyll in the chloroplasts — produces glucose and releases oxygen as
a byproduct. It happens in two main stages. The light-dependent reactions
occur in the thylakoid membranes: light energy splits water molecules,
releasing oxygen, and generates ATP and NADPH (energy-carrying molecules).
The light-independent reactions (the Calvin cycle) occur in the stroma and
use that ATP and NADPH to fix carbon dioxide into glucose — this stage
doesn't directly need light, but depends on the products of the light
reactions. Photosynthesis is the foundational energy input for nearly all
food chains on Earth, and it's also the main reason atmospheric oxygen exists
at the levels it does.

## TCP vs UDP

TCP (Transmission Control Protocol) and UDP (User Datagram Protocol) are the
two main transport-layer protocols used to send data over a network. TCP is
connection-oriented: before any data is sent, the two sides perform a
three-way handshake to establish a connection. TCP guarantees reliable,
ordered delivery — it retransmits lost packets and reorders out-of-sequence
ones — using acknowledgments and sequence numbers. This reliability adds
overhead and latency, which is why TCP is used for things where correctness
matters more than speed: web pages (HTTP), file transfers, email. UDP is
connectionless: it just fires packets ("datagrams") without a handshake, and
makes no guarantee they arrive, arrive in order, or arrive only once. That
makes it faster and lower-overhead than TCP, which is why it's used for video
calls, live streaming, and online gaming — a dropped or late packet is worse
for the experience than a slightly imperfect one. In short: TCP trades speed
for reliability; UDP trades reliability for speed.
