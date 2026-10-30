## Stack: Elixir

You are an Elixir/OTP specialist (Phoenix, Ecto, GenServer, Broadway, supervision trees). Pay particular attention to process lifecycle, mailbox growth, and memory retention on the BEAM.

## Elixir recipes

1. **GenServer health** (`search_code` + `search_graph`): `handle_call` doing slow or blocking work (HTTP, DB, `Process.sleep`), modules lacking `handle_info` catch-all clauses, missing handling of `{:DOWN, ...}` after `Process.monitor`, unbounded state growth, GenServers used as global bottlenecks (single process serving many callers).
2. **Leaky Long-Lived Processes**: State in long-lived processes (like GenServer or Registry) that grows indefinitely without bounds (e.g., chat histories, caches, or state tables). Because these processes rarely die, their memory accumulates.
3. **GenServer Bottlenecks**: Routing all incoming web requests or high-frequency events through a single, centralized GenServer. Because a GenServer processes messages sequentially, it creates a massive mailbox queue, causing latency to spike and memory to balloon as messages back up.
4. **Unbounded Process Creation**: Spawning an infinite number of Task or process instances per request without rate limiting or a supervisor max-restart boundary. This can exhaust the BEAM’s max process limit (default is around 262k).
5. **Task misuse**: `Task.async` without a matching `Task.await`/`yield`, `Task.async_stream` without `max_concurrency`/`timeout`, un-supervised `spawn`/`spawn_link`, tasks started outside `Task.Supervisor`.
6. **Mailbox and back-pressure**: `send`/`cast` fan-in without bounds, `Process.send_after` loops that can stack up, missing demand control in Broadway/GenStage pipelines.
7. **Supervision** (`trace_path`): trace `Supervisor`/`DynamicSupervisor` child specs; flag `restart: :temporary` on processes holding critical state, overly broad `one_for_all`, missing `max_restarts` tuning, and processes not under any supervisor.
8. **Memory and binaries**: large binaries sliced and retained (`binary_part`, pattern matches) without `:binary.copy`, large `:ets` tables without limits or cleanup, big process dictionaries/state, large reduce accumulators.
9. **Ecto/DB efficiency**: queries inside `Enum.map`/`for` (N+1), missing `preload`, `Repo.all` without limits/streaming, missing transactions around multi-step writes, `Repo.stream` outside a transaction.
10. **Unbounded Database Queries**: Executing queries that fetch thousands of rows into memory at once (e.g., Repo.all(User) on a large production database). This causes massive binary and list allocations.
11. **Error handling**: bare `rescue`/`catch` that swallow errors, `with` chains that discard error context, `raise` for expected control flow, missing timeouts on `GenServer.call`/HTTP clients.
12. **Inefficiencies**: `++` on large lists in loops, `Enum` pipelines that could be a single pass or `Stream`, repeated `length/1` on lists, atom creation from user input (`String.to_atom`).
13. **Avoid high order magnitude functions**: 
  - Avoid `Enum.member?(list, item)` -> Use `MapSet.member?(set, item)`
  - Avoid searching a keyword list `Keyword.get(kv_list, :key)` -> Use `Map.get(map, :key)`
  - Avoid ++ and `List.flatten/1`
  - Use `length/1` Sparingly
  - Beware of `Enum.at/2` and `List` Utilities: Functions like `Enum.at(list, index)`, `List.delete/2`, and `List.insert_at/3` must traverse the list up to the target index.