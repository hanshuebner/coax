# systemd units for oec

User units that run one [oec](https://github.com/lowobservable/oec)
session per coax port of an attached interface3.

| Unit | USB CDC | Coax port |
|------|---------|-----------|
| `oec-port1.service` | `if00` | 0 |
| `oec-port2.service` | `if02` | 1 |

The interface presents one CDC per coax port plus the capture port, so
`/dev/ttyACM*` numbering depends on enumeration order and moves when the
firmware gains or loses an interface.  The units name the ports through
`/dev/serial/by-id/` instead, and bind to the matching `.device` unit, so a
session follows its coax port rather than a device number.  That also makes
the sessions come back by themselves after a firmware reflash: the device
disappears, `BindsTo=` stops the unit, and `WantedBy=` starts it again when
the interface re-enumerates.

Note that systemd writes the dashes of that device path as `\x2d`.  The
unescaped spelling printed by `systemd-escape -p` names a unit that does not
exist, and a binding written that way never fires.

Install for the current user:

```bash
cp interface3/systemd/oec-*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now oec-port1 oec-port2
```

Adjust `ExecStart=` for the tn3270 host and the keyboard language.  `%h`
expands to the user's home directory, so the oec checkout is expected at
`~/oec` with its virtualenv in `~/oec/.venv`.
