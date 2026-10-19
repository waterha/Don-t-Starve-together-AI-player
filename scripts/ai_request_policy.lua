-- Pure per-bot request scheduling. All times are monotonic seconds; metrics use ms.
-- The manager owns chat payloads and calls Start explicitly after Take succeeds.
local Policy = {}
local PRIORITY = { periodic = 1, plan_completed = 2, plan_failed = 3, emergency = 4, chat = 5 }

local function finite(value)
    return type(value) == "number" and value == value and value ~= math.huge and value ~= -math.huge
end

local function number(value)
    local result = tonumber(value)
    return finite(result) and result or nil
end

local function milliseconds(seconds)
    -- Bounded numeric diagnostics only: never retain provider errors or payloads.
    return math.min(1000000000000, math.max(0, seconds) * 1000)
end

function Policy.New(interval)
    return {
        interval = math.max(5, number(interval) or 5),
        inflight = false,
        blocked_auth = false,
        retry_at = 0,
        rate_failures = 0,
        transient_failures = 0,
        metrics = {
            requests = 0,
            model_duration_count = 0,
            model_duration_ms = 0,
            schedule_wait_count = 0,
            schedule_wait_ms = 0,
        },
    }
end

function Policy.CanStart(state, now, reason)
    if not finite(now) or not PRIORITY[reason] or state.inflight or state.blocked_auth then
        return false
    end
    if now < state.retry_at then return false end
    local interval = math.max(5, number(state.interval) or 5)
    if state.last_start == nil then return true end
    -- Human chat must not wait a full periodic interval, but it still has a floor,
    -- never overlaps a request, and still honors authentication and rate-limit backoff.
    if reason == "chat" then return now - state.last_start >= 5 end
    return now - state.last_start >= interval
end

function Policy.Start(state, now, reason)
    if not Policy.CanStart(state, now, reason) then return false end
    state.inflight = true
    state.last_start = now
    state.started_at = now
    state.metrics.requests = state.metrics.requests + 1
    return true
end

local function error_kind(err)
    local text = type(err) == "string" and err:lower() or ""
    if err == 401 or text:match("%f[%d]401%f[%D]")
        or text:find("invalid api_key", 1, true)
        or text:find("missing api key", 1, true) then
        return "auth"
    end
    if err == 429 or text:match("%f[%d]429%f[%D]") then return "rate" end
    return "transient"
end

function Policy.Finish(state, now, err, retry_after)
    if not finite(now) then return false end
    if state.inflight then
        state.metrics.model_duration_count = state.metrics.model_duration_count + 1
        state.metrics.model_duration_ms = milliseconds(now - state.started_at)
    end
    state.inflight = false
    state.started_at = nil
    -- Finish may seed a new bot's state with its preceding character-selection error.
    -- No request or duration is charged in that case.
    if err == nil or err == false then
        state.rate_failures = 0
        state.transient_failures = 0
        state.retry_at = 0
        -- Authentication stays blocked until the world constructs a new state.
        return true
    end
    local kind = error_kind(err)
    if kind == "auth" then
        state.blocked_auth = true
        return true
    end
    local delay
    if kind == "rate" then
        state.rate_failures = math.min(4, state.rate_failures + 1)
        delay = math.min(120, 15 * 2 ^ (state.rate_failures - 1))
        local retry = number(retry_after)
        if retry and retry >= 0 then delay = math.max(15, math.min(300, retry)) end
    else
        state.transient_failures = math.min(5, state.transient_failures + 1)
        delay = math.min(60, 5 * 2 ^ (state.transient_failures - 1))
    end
    -- A later failure must never shorten a previously established cooldown.
    state.retry_at = math.max(state.retry_at, now + delay)
    return true
end

function Policy.Pending(state, reason, now)
    if not PRIORITY[reason] or not finite(now) then return false end
    if not state.pending_reason then
        state.pending_reason = reason
        state.pending_at = now
    elseif PRIORITY[reason] > PRIORITY[state.pending_reason] then
        state.pending_reason = reason
        -- Promotion retains the age of the outstanding scheduling work.
        state.pending_at = math.min(state.pending_at, now)
    end
    return true
end

function Policy.Take(state, now)
    local reason = state.pending_reason
    if not reason or not Policy.CanStart(state, now, reason) then return nil end
    local wait_ms = milliseconds(now - state.pending_at)
    state.pending_reason = nil
    state.pending_at = nil
    state.metrics.schedule_wait_count = state.metrics.schedule_wait_count + 1
    state.metrics.schedule_wait_ms = wait_ms
    return reason, wait_ms
end

return Policy
