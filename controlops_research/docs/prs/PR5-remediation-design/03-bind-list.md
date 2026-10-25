# 03 — Bind list

`$WORKSPACE` is the inspected path `/mnt/Storage/AI/Hermes/workspace`.
Tests pass a temporary root into the jail constructor. Production code does
not read a bind list from the environment.

## ControlOps content, read-write, and nothing else

| Host | Jail |
| --- | --- |
| `$WORKSPACE/runtime/locks` | `/opt/data/workspace/runtime/locks` |
| `$WORKSPACE/runtime/tmp` | `/opt/data/workspace/runtime/tmp` |
| `$WORKSPACE/runtime/out` | `/opt/data/workspace/runtime/out` |
| `$WORKSPACE/runtime/runs` | `/opt/data/workspace/runtime/runs` |

The whole workspace mount is removed. The repository, Hermes persistent
state, and LanceDB are not content binds.

The lock file is `$WORKSPACE/runtime/locks/model.lock`. The flock is taken
on the host by the infer path. The jail does not need the lock file in order
to run a command, and a jailed command is not given a way to widen binds.

## Execution substrate

Named here so D5's "unless named in the approved design pack" is satisfied.
These are not ControlOps content:

```text
--die-with-parent
--new-session
--unshare-all
--cap-drop ALL
--clearenv
--setenv PATH /usr/bin:/bin
--setenv HOME /tmp
--setenv TMPDIR /tmp
--setenv LANG C.UTF-8
--ro-bind /usr /usr
--symlink usr/bin /bin
--symlink usr/lib /lib
--symlink usr/lib64 /lib64
--symlink usr/sbin /sbin
--proc /proc
--dev /dev
--tmpfs /tmp
--dir /opt
--dir /opt/data
--dir /opt/data/workspace
--dir /opt/data/workspace/runtime
--chdir /opt/data/workspace/runtime/tmp
```

`--unshare-all` includes the network namespace. The argv builder has no
`--share-net` branch. `CONTROLOPS_ALLOW_SHARED_NET` is ignored if it appears
in the environment: it cannot add `--share-net`, and it is not documented as
a supported switch.

`--dev /dev` is a fresh device tmpfs. Inspection showed the standard nodes
only. The builder must not bind `/dev/nvidia*`, `/dev/dri`, or `/dev/kfd`.
`usr/lib64` stays, because this host's dynamic linker is reached through it.

`/tmp` inside the jail is a private tmpfs. It is not one of the four host
runtime directories. Host-visible scratch is `runtime/tmp`.

## Unmounted

```text
/root
/home
/home/proteu5
/home/proteu5/AI/Hermes/hermes-agent
/run/docker.sock
/var/run/docker.sock
/etc/shadow
/etc/ssh
/mnt/Storage
/opt/data            (host Hermes data; the jail path is a synthetic parent)
/opt/hermes
/dev/nvidia0
/dev/dri
/dev/kfd
```

A test that names the Docker socket checks the socket paths. It does not bind
`/root` or `/home` as a substitute.
