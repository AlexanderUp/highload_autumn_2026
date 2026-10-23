# etcd & ZooKeeper Playground

A hands-on guide to exploring **etcd** and **ZooKeeper** separately, using the `docker-compose.yml` from this project. Each part is self-contained, so you can do them in either order.

## Contents

0. [Setup](#0-setup)
1. [etcd](#1-etcd)
2. [ZooKeeper](#2-zookeeper)
3. [Side-by-side cheat sheet](#3-side-by-side-cheat-sheet)
4. [Mini exercises](#4-mini-exercises)
5. [Troubleshooting](#5-troubleshooting)
6. [Cleanup](#6-cleanup)

---

## 0. Setup

```bash
docker compose up -d
docker compose ps
```

Expected state:

| Service          | State                  | URL / Port                |
|------------------|------------------------|---------------------------|
| etcd             | running (healthy)      | `localhost:2379`          |
| etcd-workbench   | running                | http://localhost:8002     |
| etcd-seed        | exited (0), by design  | -                         |
| zookeeper        | running (healthy)      | `localhost:2181`          |
| zoonavigator     | running                | http://localhost:9001     |
| zk-seed          | exited (0), by design  | -                         |

Check that the seed jobs worked:

```bash
docker compose logs etcd-seed
docker compose logs zk-seed
```

You can run every command below either in a terminal inside the containers (shown here) or through the web UIs.

> **Tip:** use **two terminal windows** for the watch and ephemeral-node examples, since one terminal watches while the other changes data.

---

## 1. etcd

etcd is a strongly consistent key-value store (Raft-based). Data is a **flat keyspace**; "directories" are just key prefixes like `/demo/config/`. Every change bumps a global **revision**, and you can watch changes, attach TTL **leases** to keys, and run atomic **transactions**.

### 1.1 Open a shell helper

All commands go through `etcdctl` inside the container:

```bash
docker compose exec etcd etcdctl endpoint health
```

To save typing, define an alias for your shell:

```bash
alias etcdctl='docker compose exec -T etcd etcdctl'
```

Everything below assumes this alias. (For interactive commands like `watch`, use `docker compose exec etcd etcdctl ...` without `-T`.)

### 1.2 Cluster info

```bash
etcdctl endpoint health
etcdctl endpoint status -w table
etcdctl member list -w table
```

You should see one member, which is the leader. Note the `RAFT TERM` and `RAFT INDEX` columns.

### 1.3 Basic CRUD

```bash
# Create / update
etcdctl put /playground/hello "world"

# Read
etcdctl get /playground/hello

# Read only the value
etcdctl get /playground/hello --print-value-only

# Delete
etcdctl del /playground/hello
etcdctl get /playground/hello      # prints nothing
```

### 1.4 Explore the seeded data (prefixes)

```bash
# Everything under /demo
etcdctl get /demo --prefix

# Keys only
etcdctl get /demo --prefix --keys-only

# Just one "subtree"
etcdctl get /demo/services --prefix

# Count keys
etcdctl get /demo --prefix --count-only

# Limit results
etcdctl get /demo --prefix --limit=2

# JSON output (note the revisions!)
etcdctl get /demo/greeting -w json
```

In the JSON output, find:

- `create_revision`: revision at which this key was created
- `mod_revision`: revision of the last modification
- `version`: how many times this key has been modified since creation

### 1.5 Revisions and history (MVCC)

etcd keeps old versions of keys until they are compacted.

```bash
etcdctl put /playground/counter 1
etcdctl put /playground/counter 2
etcdctl put /playground/counter 3

# Current value and its revision
etcdctl get /playground/counter -w json

# Time travel: read the value at an older revision
# (replace N with a mod_revision from the first put, i.e. current mod_revision - 2)
etcdctl get /playground/counter --rev=N
```

Compact history up to a revision (old versions become unreadable):

```bash
etcdctl compact <revision>
etcdctl get /playground/counter --rev=<older-than-revision>   # now fails: "required revision has been compacted"
```

### 1.6 Watch for changes (two terminals)

**Terminal A**, start watching:

```bash
docker compose exec etcd etcdctl watch /playground/ --prefix
```

**Terminal B**, make changes:

```bash
etcdctl put /playground/a 1
etcdctl put /playground/b 2
etcdctl put /playground/a 10
etcdctl del /playground/b
```

Terminal A prints a `PUT` or `DELETE` event for each change. Stop with `Ctrl+C`.

Bonus: replay history with `--rev`:

```bash
docker compose exec etcd etcdctl watch /playground/ --prefix --rev=1
```

### 1.7 Leases (TTL keys), the etcd equivalent of ephemeral keys

```bash
# 1. Grant a lease with a 20s TTL (prints a lease ID)
etcdctl lease grant 20
# lease 694d8b..... granted with TTL(20s)

# 2. Attach a key to it (use your lease ID)
etcdctl put /playground/session "alive" --lease=<LEASE_ID>

# 3. Inspect remaining TTL and attached keys
etcdctl lease timetolive <LEASE_ID> --keys

# 4. Wait 20 seconds...
etcdctl get /playground/session    # gone!
```

Keep a lease alive:

```bash
etcdctl lease grant 15
# In a separate terminal (blocks, sending heartbeats):
docker compose exec etcd etcdctl lease keep-alive <LEASE_ID>
```

Revoke early (deletes all attached keys immediately):

```bash
etcdctl lease revoke <LEASE_ID>
```

### 1.8 Transactions (compare-and-swap)

A transaction has **compare** conditions, a **success** block and a **failure** block. etcdctl's interactive mode reads them from stdin:

```bash
docker compose exec -it etcd etcdctl txn --interactive
```

Type (blank line separates sections):

```
compares:
value("/playground/lock") = ""

success requests (get, put, del):
put /playground/lock "owner-A"

failure requests (get, put, del):
get /playground/lock
```

Run it once → `SUCCESS`. Run it again → `FAILURE`, and you get the current owner. That's an atomic "create if not exists", the foundation of locks and leader election.

Non-interactive variant for scripting:

```bash
printf 'mod("/playground/cas") = "0"\n\nput /playground/cas "first"\n\nget /playground/cas\n\n' \
  | docker compose exec -T etcd etcdctl txn
```

### 1.9 Distributed lock and leader election (built into etcdctl)

**Locks**: in two terminals:

```bash
# Terminal A: grabs the lock and holds it while the command runs
docker compose exec etcd etcdctl lock mylock sh -c 'echo "A has the lock"; sleep 30'

# Terminal B: blocks until A finishes
docker compose exec etcd etcdctl lock mylock sh -c 'echo "B has the lock"'
```

**Leader election**: also two terminals:

```bash
# Terminal A
docker compose exec etcd etcdctl elect my-election node-A

# Terminal B (blocks until A exits)
docker compose exec etcd etcdctl elect my-election node-B
```

Press `Ctrl+C` in A and B immediately becomes leader.

### 1.10 The HTTP/JSON gateway (no etcdctl needed)

etcd exposes a gRPC gateway. Keys and values must be **base64-encoded**:

```bash
KEY=$(printf '/playground/http' | base64)
VAL=$(printf 'hello via curl' | base64)

# PUT
curl -s -X POST http://localhost:2379/v3/kv/put \
  -d "{\"key\":\"$KEY\",\"value\":\"$VAL\"}"

# GET
curl -s -X POST http://localhost:2379/v3/kv/range \
  -d "{\"key\":\"$KEY\"}"

# Decode the value from the response
curl -s -X POST http://localhost:2379/v3/kv/range -d "{\"key\":\"$KEY\"}" \
  | python3 -c 'import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)["kvs"][0]["value"]).decode())'

# Version and health
curl -s http://localhost:2379/version
curl -s http://localhost:2379/health
```

### 1.11 Snapshot (backup and inspect)

```bash
docker compose exec etcd etcdctl snapshot save /tmp/snap.db
docker compose exec etcd etcdutl snapshot status /tmp/snap.db -w table
```

### 1.12 Using etcd Workbench (UI)

1. Open http://localhost:8002 (if prompted to log in, see the project README for default credentials).
2. Add a new connection: **host** `etcd`, **port** `2379`, no auth/TLS.
3. Browse to `/demo/` and look at the seeded keys.
4. Try: create a key, edit its value, delete it, and view its revision/lease info.
5. While the UI is open, run `etcdctl put /demo/config/log_level "info"` in the terminal and refresh to see the change.

---

## 2. ZooKeeper

ZooKeeper is a coordination service (ZAB protocol) with a **hierarchical tree of znodes**, like a filesystem. Each znode holds a small amount of data (<1 MB) and can have children. Znodes can be **persistent**, **ephemeral** (tied to a client session), and/or **sequential** (auto-numbered). Clients can set one-time **watches** on znodes.

### 2.1 Open the CLI

Interactive session:

```bash
docker compose exec -it zookeeper zkCli.sh -server localhost:2181
```

You'll get a prompt like `[zk: localhost:2181(CONNECTED) 0]`. Type `help` to list commands, `quit` to exit.

One-shot commands (without a prompt), handy for scripting:

```bash
alias zk='docker compose exec -T zookeeper zkCli.sh -server localhost:2181'
zk ls /
```

> **Important:** ephemeral nodes and watches only live as long as a *session*. A one-shot command ends its session right away, so use the **interactive** CLI for those sections.

### 2.2 Server health & info (four-letter words)

Enabled in the compose file via `ZOO_4LW_COMMANDS_WHITELIST`:

```bash
docker compose exec zookeeper bash -c 'echo ruok | nc localhost 2181'    # -> imok
docker compose exec zookeeper bash -c 'echo srvr | nc localhost 2181'    # version, mode (standalone), connections
docker compose exec zookeeper bash -c 'echo stat | nc localhost 2181'    # connected clients
docker compose exec zookeeper bash -c 'echo mntr | nc localhost 2181'    # monitoring metrics
docker compose exec zookeeper bash -c 'echo conf | nc localhost 2181'    # configuration
```

Or simply:

```bash
docker compose exec zookeeper zkServer.sh status
```

### 2.3 Explore the tree

Inside the interactive CLI:

```
ls /
ls /demo
ls -R /demo
get /demo
get /demo/services/api
```

`ls -R` lists recursively; you should see `/demo/services/api`, `/demo/services/worker` and `/demo/config/log_level`.

`/zookeeper` is a reserved subtree (quotas, config), and you can ignore it for now.

### 2.4 Basic CRUD

```
create /playground "root of my experiments"
create /playground/hello "world"
get /playground/hello
set /playground/hello "universe"
get /playground/hello
delete /playground/hello
ls /playground
```

Notes:

- `create` fails if the **parent doesn't exist** (unlike etcd, where keys are flat). Try `create /a/b/c "x"` to see the error.
- `delete` fails on znodes **with children**; use `deleteall /playground` to remove a whole subtree.

### 2.5 Node metadata (the `Stat` structure)

```
stat /demo/config/log_level
get -s /demo/config/log_level
```

Key fields:

| Field            | Meaning                                                |
|------------------|--------------------------------------------------------|
| `czxid`          | Transaction ID that created the node                   |
| `mzxid`          | Transaction ID of the last modification                |
| `ctime` / `mtime`| Creation / modification time                           |
| `version`        | Number of data changes                                 |
| `cversion`       | Number of child changes                                |
| `ephemeralOwner` | Session ID if ephemeral, otherwise `0x0`               |
| `numChildren`    | Number of children                                     |

**Optimistic concurrency with versions:**

```
create /playground/cfg "v1"
set /playground/cfg "v2" 0      # OK, version matches (0)
set /playground/cfg "v3" 0      # FAILS, the version is now 1
set /playground/cfg "v3" 1      # OK
```

### 2.6 Ephemeral nodes (use two terminals)

**Terminal A**, open interactive CLI and create an ephemeral node:

```
create -e /playground/worker-1 "I am alive"
ls /playground
```

**Terminal B**, check from another session:

```bash
docker compose exec zookeeper zkCli.sh -server localhost:2181 ls /playground
```

You'll see `worker-1`. Now in Terminal A, type `quit` (or press `Ctrl+C`). Run the command in Terminal B again → the node is **gone** (after the session closes or times out, which can take a few seconds). This is how ZooKeeper does liveness detection and service presence.

Check `ephemeralOwner` while it exists:

```
stat /playground/worker-1
```

### 2.7 Sequential nodes

```
create -s /playground/task- "job"
create -s /playground/task- "job"
create -s /playground/task- "job"
ls /playground
```

You'll get `task-0000000000`, `task-0000000001`, `task-0000000002`. The counter is managed by the parent and is monotonic. This is the building block for queues, locks and leader election.

Combine both for the classic election/lock pattern:

```
create -e -s /playground/candidate- "node-A"
```

### 2.8 Watches (two terminals)

Watches fire **once**. They need to be re-registered after each event.

**Terminal A**, interactive:

```
create /playground/watched "v1"
get -w /playground/watched
```

**Terminal B**:

```bash
docker compose exec -T zookeeper zkCli.sh -server localhost:2181 set /playground/watched "v2"
```

Terminal A prints:

```
WATCHER::
WatchedEvent state:SyncConnected type:NodeDataChanged path:/playground/watched
```

Other watch flavors:

```
ls -w /playground           # fires on child added/removed (NodeChildrenChanged)
stat -w /playground/x       # fires on creation/deletion/change (works for non-existent nodes)
```

Persistent watches (ZooKeeper 3.6+) don't need re-registration:

```
addWatch /playground
addWatch -m PERSISTENT_RECURSIVE /playground
```

### 2.9 ACLs (access control)

```
getAcl /playground
# 'world,'anyone : cdrwa   (default: open to everyone)

# Make a node read-only for everyone
setAcl /playground/cfg world:anyone:r
set /playground/cfg "nope"       # -> Authentication is not valid / Insufficient permission
```

Permissions: **c**reate, **d**elete, **r**ead, **w**rite, **a**dmin. To reset, you'd need admin rights, so create a fresh node, or use `digest` auth:

```
addauth digest alice:secret
create /playground/private "secret data" auth:alice:secret:cdrwa
```

### 2.10 Quotas (optional)

```
setquota -n 5 /playground      # limit to 5 nodes (soft limit: logs a warning)
listquota /playground
delquota /playground
```

### 2.11 Using ZooNavigator (UI)

1. Open http://localhost:9001. It should auto-connect to `zookeeper:2181`. If it asks for a connection string, enter `zookeeper:2181`.
2. Browse `/demo` and open `config → log_level`.
3. Create a new child node (there are options for persistent/ephemeral/sequential), edit its data, delete it.
4. In the terminal, run `create /demo/from-cli "hi"` and refresh the UI.

---

## 3. Side-by-side cheat sheet

| Task                     | etcd (`etcdctl`)                          | ZooKeeper (`zkCli.sh`)                    |
|--------------------------|-------------------------------------------|-------------------------------------------|
| Data model               | Flat key-value (prefixes)                 | Hierarchical znode tree                   |
| Write                    | `put /k v`                                | `create /k v` / `set /k v`                |
| Read                     | `get /k`                                  | `get /k`                                  |
| List children / prefix   | `get /p --prefix --keys-only`             | `ls /p` (`ls -R /p`)                      |
| Delete                   | `del /k` (`del /p --prefix`)              | `delete /k` (`deleteall /p`)              |
| Missing parent           | Fine, keys are flat                       | Error, must create the parent first       |
| Ephemeral keys           | Lease: `lease grant` + `put --lease`      | `create -e`, tied to the client session   |
| Auto-numbering           | Not built-in (use revisions)              | `create -s`                               |
| Watch                    | `watch k [--prefix]` (streaming, replay)  | `get -w` (one-shot) / `addWatch` (3.6+)   |
| History / time travel    | `get --rev=N` (until compaction)          | None (only current state)                 |
| Atomic ops               | `txn` (compare/then/else)                 | `multi`, versioned `set`                  |
| Built-in lock/election   | `etcdctl lock` / `elect`                  | Recipes (e.g. Curator), manual            |
| Protocol                 | gRPC + HTTP/JSON gateway                  | Custom binary protocol                    |
| Consensus                | Raft                                      | ZAB                                       |
| Typical users            | Kubernetes, CoreDNS, Patroni              | Kafka (legacy), HBase, Hadoop, Solr       |

---

## 4. Mini exercises

### Exercise 1: Service registry

**etcd**: register two instances with leases, then discover them:

```bash
etcdctl lease grant 60                       # note ID as L1
etcdctl put /registry/web/instance-1 "10.0.0.1:80" --lease=<L1>
etcdctl lease grant 60                       # note ID as L2
etcdctl put /registry/web/instance-2 "10.0.0.2:80" --lease=<L2>

etcdctl get /registry/web/ --prefix
etcdctl lease revoke <L1>                    # simulate instance-1 dying
etcdctl get /registry/web/ --prefix          # only instance-2 remains
```

**ZooKeeper**: same idea with ephemeral nodes (interactive CLI):

```
create /registry ""
create /registry/web ""
create -e /registry/web/instance-1 "10.0.0.1:80"
create -e /registry/web/instance-2 "10.0.0.2:80"
ls /registry/web
```

Then `quit` and look again from a new session, and the instances are gone.

### Exercise 2: Dynamic config with watches

1. Set a config value and watch it:
   - etcd: `etcdctl put /app/feature_x off`, then `watch /app/feature_x` in another terminal.
   - ZooKeeper: `create /app ""`, `create /app/feature_x off`, then `get -w /app/feature_x`.
2. Flip the value from a second terminal and confirm the watcher fires.
3. Notice the difference: etcd's watch **stays open** and streams every event, while ZooKeeper's watch **fires once**.

### Exercise 3: Leader election by hand

- **etcd**: run the `elect` command from section 1.9 in two terminals.
- **ZooKeeper**: in two interactive CLIs create `create -e -s /election/c- "node-X"`. The node with the **lowest sequence number** is the leader. Quit that session and see that the next-lowest node takes over.

### Exercise 4: Optimistic locking

- **etcd**: use a `txn` that compares `mod("/key")` to the revision you read.
- **ZooKeeper**: use `set /key value <version>` with the version from `stat`.

### Exercise 5: Break it on purpose

```bash
docker compose restart etcd
etcdctl get /demo --prefix          # data persists (volume etcd-data)

docker compose restart zookeeper
docker compose exec -T zookeeper zkCli.sh -server localhost:2181 ls -R /demo   # persisted too
```

Then compare what happens to **leases** (etcd) and **ephemeral nodes** (ZooKeeper) across the restart. Leases keep their remaining TTL, while ephemerals are removed once their sessions are gone.

---

## 5. Troubleshooting

| Symptom                                            | Fix                                                                                          |
|----------------------------------------------------|----------------------------------------------------------------------------------------------|
| `etcdctl: command not found` on the host           | Use the alias in 1.1; `etcdctl` lives inside the container                                   |
| Workbench can't connect to etcd                    | Use host `etcd` (not `localhost`) when the UI runs in Docker                                 |
| `nc: command not found` in the ZooKeeper container | Use `docker compose exec zookeeper bash -c 'exec 3<>/dev/tcp/localhost/2181; echo ruok >&3; cat <&3'` |
| `... is not in the whitelist`                      | The command isn't listed in `ZOO_4LW_COMMANDS_WHITELIST` in the compose file                |
| Ephemeral node doesn't disappear                   | Wait for the session timeout (a few seconds), or make sure the CLI session really exited     |
| ZooKeeper `create` fails with `NoNode`             | The parent znode doesn't exist; create parents first                                         |
| Port already in use                                | Change the host port mapping (e.g. `"12379:2379"`) in `docker-compose.yml`                   |
| Seed data missing                                  | `docker compose up etcd-seed zk-seed` to re-run the seeders (ZooKeeper nodes won't be recreated if they already exist, and the errors are harmless) |

---

## 6. Cleanup

Stop everything but keep data:

```bash
docker compose down
```

Stop and wipe all data (volumes):

```bash
docker compose down -v
```

Remove just your experiments, not the seeded `/demo`:

```bash
etcdctl del /playground --prefix
docker compose exec -T zookeeper zkCli.sh -server localhost:2181 deleteall /playground
```