# Task 10: Production Async Resilience

In software engineering, "Resilience" is the ability of a system to gracefully handle failures, spikes in traffic, and external outages without crashing completely. This task requires us to build four distinct layers of armor around NeuroFlow.

---

## 1. The Circuit Breaker Pattern

**The Concept:**
Think of a physical circuit breaker in your house. If you plug too many appliances into one outlet, the circuit breaker "trips" (opens) to stop the flow of electricity, preventing a fire. 
In software, if we are calling an external service (like OpenAI) and they go down, our system might hang for minutes waiting for a response, eventually crashing our own servers because all our workers are stuck waiting. 

A software Circuit Breaker sits between our app and the external API. It has three states:
1. **CLOSED (Normal)**: Everything is fine. Requests flow through normally.
2. **OPEN (Failing)**: If the external API fails 5 times in a row, the breaker trips! It immediately blocks all future requests for a set time (e.g., 60 seconds). Instead of waiting for OpenAI to fail again, it fails instantly, saving our system resources.
3. **HALF-OPEN (Testing)**: After 60 seconds, it carefully lets 3 requests through. If they succeed, it closes the breaker (back to normal). If they fail, it trips wide open again.

**Our Implementation:**
We will create a `CircuitBreaker` class backed by **Redis**. Why Redis? Because we have multiple Docker workers running at once. If Worker A notices OpenAI is down, it updates Redis, and instantly Worker B knows to stop sending requests too. We'll wrap all our external LLM calls with this breaker.

---

## 2. Rate Limiting (Token Bucket)

**The Concept:**
Rate limiting is how you stop users (or yourself) from spending too much money or overwhelming a server. The task asks us to implement the **Token Bucket Algorithm**.
Imagine a literal bucket that holds 3,000 coins (tokens). Every second, we drop 50 new coins into the bucket. Every time you make a request to OpenAI, you must take 1 coin out. If the bucket is empty, you have to wait for new coins to drop in.

**Our Implementation:**
We need to apply this in three places:
1. **Global Provider Limit**: Prevents NeuroFlow from exceeding OpenAI's hard limits (e.g., 3000 tokens/min) so we don't get banned.
2. **Per-Pipeline Limit**: Stops a single user's pipeline config from hogging all the resources.
3. **API Endpoints**: Stops malicious users from spamming our `/ingest` or `/query` APIs (e.g., limiting them to 10 requests per hour). 

We will use Redis to store these "buckets" so the token counts are perfectly synced across all our background workers.

---

## 3. Backpressure

**The Concept:**
Imagine working at a fast-food restaurant. If the cashier takes 100 orders in a minute, but the kitchen can only cook 5 burgers a minute, the kitchen gets overwhelmed, quality drops, and eventually, the kitchen stops working entirely. 
**Backpressure** is the cashier telling the customer, "Sorry, the kitchen is full right now, please come back in 5 minutes." It pushes the pressure back onto the user rather than letting it build up internally.

**Our Implementation:**
Right now, users can throw thousands of PDFs at our `/ingest` endpoint, filling up our Redis background queue endlessly. We will add a check:
- If the Redis queue has > 50 items, we accept the document but return a `202 Accepted` with a warning: *"Hey, we are busy, this will take a while."*
- If the queue has > 100 items, we refuse the document with a `503 Service Unavailable`: *"We are completely full. Try again later."*

---

## 4. Timeout Management

**The Concept:**
A timeout is simply setting a strict stopwatch on an operation. If an external API usually responds in 2 seconds, but suddenly takes 5 minutes, we shouldn't wait. We should give up after 10 seconds and throw an error. This frees up the system to do other ticketing tasks rather than being held hostage by a slow API.

**Our Implementation:**
We will create a central `timeouts` dictionary mapping operations to maximum wait times (e.g., embeddings get 10 seconds, but heavy evaluations get 120 seconds). We'll enforce these strictly using Python's `asyncio.wait_for()`.

---

## Technical Action Plan

1. **Setup**: Create the `backend/resilience/` module directory.
2. **Circuit Breaker (`circuit_breaker.py`)**: Build the Redis-backed state machine.
3. **Rate Limiter (`rate_limiter.py`)**: Build the Redis Token Bucket algorithm.
4. **Backpressure (`backpressure.py`)**: Build the queue depth checker for `/ingest`.
5. **Timeouts (`timeout_manager.py`)**: Build the centralized timeout enforcer.
6. **Health Endpoint (`backend/api/health.py`)**: Upgrade our existing `/health` endpoint to aggregate the status of our circuit breakers and queue depths.
7. **Integration**: Inject these tools into our existing ingestion, query, and finetune pipelines!
