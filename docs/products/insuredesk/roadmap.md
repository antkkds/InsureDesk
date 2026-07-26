# Roadmap

## Generation 1 — COMPLETE

All PI-1 through PI-20 development phases are complete.

```
PI-1   Document Intelligence       ✓
PI-2   Bridge                      ✓
PI-3   Tool Runtime                ✓
PI-4   Blueprint                   ✓
PI-5   Query                       ✓
PI-6   Portfolio                   ✓
PI-7   Version                     ✓
PI-8   Lifecycle                   ✓
PI-9   Financial                   ✓
PI-10  Market                      ✓
PI-11  Workflow                    ✓
PI-12  Synchronization             ✓
PI-13  Communication               ✓
PI-14  Automation                  ✓
PI-15  Business Intelligence       ✓
PI-16  Team Collaboration          ✓
PI-17  Enterprise Integration      ✓
PI-18  Predictive + Family         ✓
PI-19  Knowledge + Reasoning       ✓
PI-20  Autonomous Operations       ✓
```

## Next: Productization

Development phases are frozen. No PI-21+. The next work is organized in parallel tracks.

### Track A: Portal Validation (NOW)
- [ ] Test Great Eastern live browser login
- [ ] Capture real selectors with Inspector
- [ ] Fix selector mismatches
- [ ] Test Allianz and AIA portals
- [ ] Verify session persistence

### Track B: Windows Packaging
- [ ] PyInstaller build on Windows
- [ ] Test on clean Windows 10 VM
- [ ] Test on clean Windows 11 VM
- [ ] Installer creation (Inno Setup or similar)
- [ ] Auto-update mechanism

### Track C: Pilot Readiness
- [ ] All items in PILOT.md checklist
- [ ] 3 real agents test for 1 week
- [ ] Bug fixes from pilot feedback
- [ ] Performance tuning

### Track D: Enterprise Readiness
- Audit Center / Compliance reports
- Permission matrix / RBAC
- Encryption management
- Backup and restore

### Track E: Ecosystem
- Gmail / Outlook integration
- e-signature providers
- Insurer API gateways
- Payment gateways

## Future Tracks (not yet scheduled)

- **AI Quality** — Hallucination detection, confidence scoring, multi-step validation
- **Scale** — Multi-agency, distributed scheduling, caching
- **Marketplace** — UIP-AI app marketplace for multiple industries
- **Industry Expansion** — ClinicDesk, LegalDesk, EduDesk on same platform
- **Developer Platform** — SDK, REST API, webhooks, plugin SDK
