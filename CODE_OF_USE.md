# Code of Use (Authorized Use Policy)

> Scarlight is an offensive-security tool. Use of Scarlight is conditional on this policy. Contributors agree to it. Operators agree to it on first run.

---

## 1. Authorized use only

You may use Scarlight only against systems for which you have **explicit, documented, current authorization** to perform security testing. Authorization sources include:

- Written engagement contracts (Master Services Agreement + Statement of Work) for penetration testing.
- Published Rules of Engagement of a bug-bounty program for assets explicitly named in scope.
- CTF event participation against CTF-event-provided assets.
- Cyber-range and lab environments you own or are licensed to use.
- Systems you personally own and operate.
- Research environments where the system owner has agreed in writing to your testing.

If you do not have explicit authorization, **do not run Scarlight against the target**. Scarlight's authorization guard is a first measure — it refuses to start an engagement without a valid scope configuration — but the legal and ethical responsibility is yours.

---

## 2. Prohibited uses

You may not use Scarlight to:

1. Conduct security testing against systems you are not authorized to test.
2. Conduct denial-of-service attacks, resource-exhaustion attacks, or otherwise affect target availability outside of explicitly scoped engagements.
3. Exfiltrate, retain, or distribute data you discover beyond what is necessary to demonstrate a finding to the authorized stakeholder.
4. Target critical infrastructure, medical devices, transportation systems, ICS/SCADA systems, financial-clearing systems, or election infrastructure — except under formal engagement with the system operator, with documented authorization explicitly recorded in the engagement's scope configuration.
5. Build, distribute, or deploy malware (ransomware, info-stealers, wormable payloads, persistent C2 implants) intended for unauthorized deployment.
6. Circumvent, disable, or modify Scarlight's authorization guard, or tamper with its session records, to obscure your activity.

---

## 3. Responsible disclosure

If Scarlight identifies a vulnerability:

- Report through the affected vendor's published security disclosure channel.
- Honor the disclosure timeline of the relevant bug-bounty program, or default to 90 days from notification.
- Do not publicly disclose unpatched, unmitigated vulnerabilities outside of recognized disclosure programs.

---

## 4. Restricted capability list

The following capability classes are **not** included in the default Scarlight skill library. If community skill packs distribute them, enabling such a skill is an explicit, deliberate operator choice — never a default — and remains subject to this policy.

- Persistence mechanisms (rootkits, scheduled-task implants, registry persistence).
- Worm / lateral-movement automation that can affect more than one host without per-target authorization.
- Credential-harvesting against systems the operator does not own.
- 0day weaponization for undisclosed CVEs.
- ICS/SCADA-targeting exploits.
- Mobile-device-management bypass / device-rooting payloads.
- Cryptographic key extraction from HSMs / TPMs not owned by the operator.

We reserve the right to refuse contributions of skills that fall into these classes without commensurate gating.

---

## 5. Operator responsibility

Operators acknowledge:

- They have read this policy.
- They are legally authorized to conduct each engagement they initiate.
- Engagement contracts they sign in Scarlight reflect their actual authorization.
- They are responsible for the lawful retention, handling, and disclosure of any data discovered.
- They are responsible for compliance with applicable laws in their jurisdiction (Computer Fraud and Abuse Act in the United States, Computer Misuse Act 1990 in the United Kingdom, equivalent statutes elsewhere).

---

## 6. Contributor agreement

By contributing to Scarlight, you agree:

- Your contribution is offered under Apache 2.0.
- Your contribution does not knowingly include vulnerabilities, backdoors, or capabilities prohibited above.
- Skills you submit declare their payload class accurately.
- You will participate in good-faith disclosure for any Scarlight-internal vulnerabilities you discover.

---

## 7. Enforcement

Scarlight maintainers reserve the right to:

- Reject contributions that violate this policy.
- Disavow skill packs that violate this policy.
- Cooperate with law enforcement when presented with valid legal process.
- Maintain a public registry of revoked / disavowed contributions.

We will not assist law enforcement in identifying lawful security researchers. Authorized use deserves protection; misuse does not.

---

## 8. No warranty

Scarlight is provided as-is. The maintainers make no warranty regarding fitness for any particular use and accept no liability for misuse. See the [LICENSE](./LICENSE) for the legal terms; this Code of Use is the ethical framing.
