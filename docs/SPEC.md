# Sift: A Cost-Aware Chat Router, Build Spec for Claude Code

This document is the complete specification for building and testing a cost-aware chat system. It is written for a coding agent (Claude Code) and for its owner, Akhil. Read it fully before writing any code. Where something is unverified, it says so. Do not invent API details: check the current documentation for each provider before coding against it.

## 1. What this project is

A chatbot with a small decision step in front of every reply. For each user message, the decision step chooses (a) which stored topic groups of the conversation to send as context and (b) which answering model to use, then checks whether acting on those choices actually saves money once prompt-cache costs are counted. The goal is a measured result such as: "With the same dollar budget, this system answers X more questions correctly than an existing router," or "N% of the accuracy at M% of the cost."

This is a portfolio project for AI engineer job applications. The result must be honest and reproducible. A negative result (the design does not beat a simple baseline) is acceptable and must be reported as such.

## 2. The core idea in plain words

- Pruning (leaving irrelevant history out of the prompt) and model routing (using a cheaper model for easy questions) are each already common, and stacking them as separate steps is already standard practice. That alone is not novel.
- The angle here is to treat model choice and context size as one joint decision, and to count the prompt-cache penalty before acting. Providers cache the start of a prompt per model. Switching models, or changing the start of the prompt, loses the cache for everything after the change, so that part of the history can be billed again at full price. Changing only the end of the prompt loses almost nothing, so the penalty depends on position. A router that switches or prunes too eagerly can cost more than not routing at all.
- Closest existing work, from reading abstracts and introductions only: "Whose Turn Is It? Context-Guided Model Routing for Stateful Agents" (arXiv 2610.19292) covers cache-aware routing at the turn boundary for agent tasks. DialRouter (arXiv 2604.12385) treats multi-turn routing as sequential decisions. MTRouter (arXiv 2604.23530) picks a model per turn under a cost budget using learned embeddings and takes history as given. None of these was found to decide pruning and model choice together. This gap is narrow and unconfirmed. Read these papers properly before making any novelty claim.

## 3. Terms that must not be confused

- Context: the text sent to the answering model on one call. System prompt, earlier messages, earlier replies, and the new message.
- Cache: a provider billing discount applied when the start of the new prompt exactly matches the start of a recent prompt. It is not stored answers. The model still generates a fresh reply every time. Nothing in this project stores or controls the cache directly. The code only controls how prompts are built, so the start stays identical when possible. The cache is also not the same as the stored conversation: the full conversation, grouped by topic, is kept by the project's own code, and the cache only makes repeated prompt starts cheaper.
- Decision model: a model that does not write text. It receives a state plus typed questions and returns answers with probabilities.
- Answering model: the ordinary chat model that writes the reply, for example a small, medium, or large Claude model. It is separate from the decision model, and no model supervises the decision model.
- Topic group: a short label plus the ordered messages that belong to one topic. Messages are stored once with unique IDs, and a message can belong to more than one group.

## 4. The decision model (Jev) and its alternatives

The primary decision model is Jev from TypeSafe AI, used as a hosted API. Facts from its documentation and independent guides (verify against current official docs before coding):

- It is not a chat model and writes no text. The code sends a state and a map of named, typed questions. It returns typed answers with probabilities.
- Exactly three question types: Noul (yes or no, returns probability of yes), Choice (one option from up to 255, returns the full distribution; options go in a field called criteria, each with a description), and Score (position on an ordered scale of 2 to 10 levels).
- All questions in one request run in parallel against one state, and the state is billed once.
- Input is text only. A request takes about 64,000 tokens, of which about 32,000 is the budget for the state plus the longest question. Long histories must be shortened before sending, which is another reason the state contains group labels and recent turns, not the whole conversation.
- Reported pricing is about $0.042 per million input tokens with free output, and reported latency is roughly 70 to 500 ms. Vendor speed and cost claims were measured on the vendor's own workflows. Treat them as ceilings and verify.
- TypeSafe has not published Jev's architecture, weights, or a technical paper.
- Calibration means the probabilities are honest on average, not that every answer is right. Use one confidence threshold per action, scaled to the cost of being wrong. Include a none-of-the-above option in each Choice so it is not forced into a wrong answer. Pin the model version, because thresholds tuned on one release may not hold on another.
- A research paper reports that short added context can flip a decision model's answer, so the state sent to it must be clean and compact.

Alternatives with a similar interface exist, so the code must be model-agnostic behind one small interface: Microsoft-Decision-1 (hosted, weights not public, claims slightly higher accuracy and lower latency than Jev in its own tests), OpenAI's Decisions API, and open options such as SemIf, Kev, Laya, and InnerJev. Check each one's current availability and license. Building behind an interface makes it possible to compare two or three decision models as an extra experiment.

## 5. System design

The system keeps the whole conversation stored in code, grouped into topic groups. A topic group is a short label plus the ordered messages that belong to it, for example a weather group and a Hulk group. Nothing is ever deleted. For each new message, the decision model chooses which stored groups to send as context, and code builds the prompt from those groups. Per user message, the flow is:

1. State building (code). Build a compact state for the decision model: the new message, the label of each existing topic group (cap this at the five most recently used groups, because every extra question adds input tokens), the last few turns, and short facts from code such as history length in tokens, which model is currently answering, and which prompt prefixes are likely still cached. Keep it well under the decision model's limit.
2. Decision call (one request, several questions, to the decision model):
   - Group selection, done as one yes-or-no (Noul) question per existing group, such as include\_group\_weather and include\_group\_hulk, plus one Noul for is\_new\_topic. Do not use a single Choice question for this. A Choice returns probabilities that sum to one, so a message that belongs to two groups, like "will the rain ruin my Hulk outdoor screening", splits its probability, for example 45% and 45%, and neither group clears a high threshold. Separate yes-or-no questions let both groups score high at once. This replaces asking the decision model to judge every old message one by one.
   - A Choice for which answering model should handle the message, with one option per model on the menu plus none of the above. Each option's description is written by the project owner and grounded in measured results (see section 7), not in social media opinions.
   - A Score for difficulty, easy to very hard.
   - A Noul asking whether the message refers back to something specific in earlier content.
3. Policy layer (code). Apply a separate confidence threshold per action. Leaving a group out needs high confidence. Staying on the current model needs almost none. If confidence is below threshold, use the safe default: include the groups that were used last turn and stay on the current model. Include the last couple of turns only as a fallback: when group-selection confidence is below threshold, or when the Noul asking whether the message refers back to something specific returns yes. When the decision model is confident that the message belongs only to certain groups and does not refer to the immediately preceding turn, send just those groups plus the new message. Forcing the last turns in every time would pull unrelated text into the prompt, for example Hulk messages into a weather prompt, add cost, and change the prompt start. If the decision model says is\_new\_topic, code creates a new group. The group's label is the first sentence, or the first 100 characters, of the user's first message in it. Do not call any model to write the label, because that adds a paid call per new topic. Do not add the assistant's reply to the label, because longer state text can flip a decision model's answer.
4. Cache arithmetic (code, not a model). Prefix caching only discounts the part of the prompt that matches the start of a recent prompt on the same model, so the penalty depends on position. Changing something near the start of the prompt loses the cache for everything after it. Changing something near the end loses almost nothing. Treat each combination of groups as its own prefix: the weather group alone, the Hulk group alone, and weather plus Hulk are three different prompt starts, and a prefix warmed by one does not discount another. Compute, for the proposed prompt, how many tokens would still match a warm prefix on the proposed model, and compare the cost of this prompt with the cost of the alternative of staying on the current model and prompt. Act only if the saving is larger. Staying put is always allowed. Track which prefixes are warm, per model, with an expiry time, because provider caches expire after a few minutes of inactivity. Use each provider's current cache pricing, expiry time, and minimum cacheable length from its documentation, since these differ by provider and change.
5. Build the final prompt (code). Concatenate the chosen groups, deduplicating any message that appears in more than one chosen group by its message ID, so the model never sees the same message twice. Keep messages in the order they were originally sent, then append the new message at the end. Keeping a group's order stable is what lets a returning topic reuse the same prompt start.
6. Answer call. Send the prompt to the chosen answering model. Add the new message and the reply to every group it belongs to, storing each message once with a unique message ID and letting groups reference it, so a message shared by two groups is stored once and deduplicated when both groups are sent.
7. Logging (code). For every turn, write one record to a log file: the decision model name and version, the question definitions, the returned probabilities, the thresholds used, which groups were included and which were left out, the model chosen, the action taken, the prompt tokens, cached tokens read and written as reported by the provider, the cost, and later whether the answer was correct.

Who does what: the decision model judges, code stores the topic groups, calculates, and builds prompts, the provider handles the cache automatically, and the answering model writes the reply. No second model supervises the decision model, in the live path or elsewhere. A supervisor in the live path would add a model call to every message and remove the savings, and the decision model has no memory and cannot be told anything mid-chat. Mistakes are corrected between runs by changing thresholds, option descriptions, group labels, or the state format. The tool for finding mistakes is the log plus a short analysis script, not another model. The script reads the log and reports numbers such as how often a needed group was left out, how often a model switch lost money to re-billing, and how well the probabilities were calibrated. Answer correctness comes from the benchmark's known right answers. A person reads the script's output and decides what to change. Nothing changes thresholds automatically.

## 6. Worked example

Messages: (1) what is the weather right now, (2) is it going to rain today, (3) what color is the Hulk, (4) who is the Hulk's girlfriend, (5) when is sunrise.

Turns 1 and 2: at message 1 there are no groups yet, so the is\_new\_topic question scores high and code creates a weather group, labeled with the first sentence of message 1. At message 2, the include\_group\_weather question scores high and is\_new\_topic scores low, so message 2 joins the weather group. The prompt for turn 2 is the weather group plus the new message, and that prefix becomes warm on the chosen model.

Turn 3: include\_group\_weather scores low and is\_new\_topic scores high. Code creates a Hulk group and sends only the new message. This costs almost nothing, and it can go to a cheap model with no re-billing penalty because there is no history to re-bill. The weather prefix is not deleted. It simply stays warm until it expires.

Turn 4: include\_group\_hulk scores high and include\_group\_weather scores low. The prompt is the Hulk group plus the new message. The weather group is left out. The last-turns fallback is not triggered, because confidence is high.

Turn 5: include\_group\_weather scores high and include\_group\_hulk scores low. The prompt is the weather group plus the new message, and the two Hulk turns are not forced in, because confidence is high and the message does not refer back to the previous turn. If the weather prefix is still warm on the original model, the cache arithmetic sees that going back to that model costs little and the weather part is billed at the discounted rate. If the prefix has expired, the arithmetic sees there is no discount to protect and picks the cheapest adequate model.

A correction to an earlier draft of this spec: it claimed that skipping a message breaks the cache from that point and that the code would usually keep the message. That was too crude. The cost of dropping a message depends on how much text sits after it. Dropping the most recent message costs almost nothing, and dropping something near the start of a long prompt can cost a lot. The topic-group design avoids most of this, because each group keeps a stable internal order.

Also test the hard cases: a message that needs two groups at once, such as "will the rain ruin my Hulk outdoor screening", where both include\_group\_weather and include\_group\_hulk should score high and the shared message must be stored once and deduplicated when both groups are sent, a vague message like "and the other one?" that only makes sense with the last turn, a topic that returns after the cache has expired, and a topic that returns while the cache is still warm. These should all be test cases. This example should be one of them.

## 7. Build and test plan

Work in small steps. Stop and report after each step. Do not build ahead.

Step 0, setup. Create a repository with a clear structure. Choose a language (Python is suggested). Store API keys in environment variables, never in code. Confirm which providers and models are available and their current prices and cache rules by reading their documentation. Record the findings in a file in the repository.

Step 1, decision model smoke test. Use the decision model's Playground or API to send five hand-written states and questions. Confirm the response format, latency, and cost. Do not build further until this works.

Step 2, the answering-model menu. Use the Claude API with three models from the same provider so cache behavior is consistent: Haiku 5.5 as the small model, Sonnet 5.5 as the medium model, and Opus 5.5 as the large model. Before coding, read the official pricing page (platform.claude.com/docs/en/about-claude/pricing) and the prompt caching page (platform.claude.com/docs/en/build-with-claude/prompt-caching), and record the exact model identifiers, input and output prices, cache write and cache read prices, cache lifetimes, and minimum cacheable prompt length for each model, with the date you read them. The figures below came from web search results on November 1, 2026, and were not verified against the official pages, so treat them as starting points only. Reported figures: Opus 5.5 was released September 22, 2026 at $4 per million input tokens and $20 per million output tokens. A cache write costs 1.25 times the base input price for the 5-minute lifetime, or 2 times for the 1-hour lifetime. A cache read costs 5% of the base input price on Opus 5.5 and Sonnet 5.5, and about 10% on other models, though sources disagree on the exact multiplier for Haiku 5.5, so check it. One source gives a minimum cacheable prompt of 512 tokens, but it is unclear which models that applies to, so check each. Haiku 5.5 and Sonnet 5.5 prices differed across sources, so do not assume them. Because reads are so cheap on Opus and Sonnet, re-billing a long history after a switch or a prompt-start change is expensive, which is why the cache arithmetic in section 5 matters. Also write the answering-model option descriptions for the decision model here, grounded in the measured results from step 4, not in guesses.

Step 3, the question set. Build about 50 question-answering tasks with known correct answers, borrowed from existing benchmarks, not invented. Add about ten multi-turn conversations of 8 to 12 turns each with deliberate topic switches and difficulty changes, including the weather and Hulk example. Make the conversations long enough that prompt caching actually applies, since providers usually only cache above a minimum prompt length.

Step 4, ground truth for model choice. Run every question through every model on the menu and record which answered correctly and at what cost. This is what the model option descriptions are written from, and it is the ground truth for scoring the decision model's model choice. Judge open-ended answers with a stronger model only as soft evidence.

Step 5, baselines. Implement the expensive default (one large model, full history), and a simple router baseline. A simple rule router, such as one based on message length or keywords, is the first baseline. If time allows, add RouteLLM as an open-source, reproducible baseline. The OpenRouter Auto Router is an optional extra.

Step 6, the decision pipeline. Implement the flow in section 5 behind an interface so the decision model can be swapped. This includes the topic-group store, the warm-prefix tracker with expiry, and the log file. Write the log analysis script in this step.

Step 7, the three runs on the multi-turn chats. Run never-switch-or-prune, always-follow-the-decision-model with no cache check, and the full design with the cache check. Read cache read and cache write token counts from each provider response to see exactly when the cache hit and when it re-billed.

Step 8, evaluation. Report accuracy and total cost, including the decision model's own cost and cache re-billing. Report the decision model's accuracy separately for pruning level and for model choice, and report both error types: a wrong drop loses context the user needed, and a wrong switch pays the cache penalty for nothing. Check calibration: when it says 90%, is it right about 90% of the time? Test A: give the system and a baseline the same dollar budget and count correct answers. Test B: same questions, compare accuracy and total cost. Report a tradeoff curve, not a claim of identical accuracy.

Step 9, decide. If the decision-model design does not beat the simple router on this pilot, report that honestly and change the design before scaling up.

## 8. Known risks

- The biggest unknown is the model-choice question. The decision model has never seen how the answering models perform, so it can only match the message wording to the option descriptions written for it. Those descriptions must come from measured results. This is what the pilot tests first.
- Wrong group choices lose context the user needed, for example sending only the Hulk group when the message also needed the weather group. The multi-group option, the safe defaults, and the keep-recent-turns rule limit this. Topic groups also depend on good labels, and a mislabeled or merged group will mislead the decision model.
- Changing the start of the prompt reduces cache hits, and caches expire. The cache arithmetic and the warm-prefix tracker exist for this reason.
- The decision model's context limit means long histories need compact states, and a bad summary leads to bad decisions.
- Vendor claims about speed and cost are unverified. Measure them.
- Cache pricing and minimum lengths differ by provider and change over time.
- Novelty is unconfirmed. Read the closest papers fully, plus DyCP (arXiv 2601.07994) and the Conversation Tree Architecture paper (arXiv 2603.21278), before claiming anything is new.
- Existing work already uses decision models as routers and for context relevance, but separately. No evidence was found of both being done as one joint decision with a cache penalty, though the search was limited.

## 9. Rules for the coding agent

- Do not invent API fields, prices, or limits. Read the current documentation and record the source and date.
- Keep the code small and readable. This is a portfolio project that will be read by interviewers.
- Log everything described in section 5 step 7 from the first run, and write the analysis script before running the full experiments.
- Make every experiment reproducible: fixed question sets, pinned model versions, recorded settings, and saved raw results.
- Report results honestly, including failures. Never tune thresholds on the same questions used for the final report. Hold out a separate set.
- Ask the owner before spending significant money on API calls. Estimate the cost of each run first.

## 10. Success criteria

The project succeeds if it produces a reproducible, honestly measured comparison of the three setups with cache costs counted, and a clear answer to whether the joint decision beats the simple router. A clear negative result with good measurement is still a valid and publishable portfolio outcome. A headline number is only used if the data supports it.
