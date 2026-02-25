# Security Policy – ZPTTLink

ZPTTLink bridges Zello via (BlueStacks or Waydroid) to radio hardware using an All-In-One Cable (AIOC) for audio and PTT control.  
Because it interfaces with RF networks, local USB devices, and optionally remote systems, security must be taken seriously.

---

## Reporting a Vulnerability

If you discover a security vulnerability:

- Do NOT open a public issue.
- Email the maintainer directly or use GitHub’s Private Vulnerability Reporting feature.
- Include:
  - A clear description of the issue
  - Steps to reproduce
  - Affected version(s)
  - Any logs or screenshots (sanitized)

Please allow reasonable time for investigation and patching before public disclosure.

Responsible disclosure is required.

---

## RF Network & Voice Privacy Warning

ZPTTLink transmits and receives audio over:

- Internet-based services (e.g., Zello)
- RF radio networks (GMRS, amateur, etc.)

These communications:

- May be monitored
- May be recorded
- May not be encrypted end-to-end (depending on configuration)
- Are subject to local radio regulations

DO NOT transmit:

- API keys
- Authentication tokens
- Passwords
- SSH private keys
- Personal sensitive data
- Financial information

Assume all RF traffic is public.

---

## USB & Hardware Security

ZPTTLink interacts with:

- USB sound devices
- USB serial interfaces
- PTT control adapters
- Virtual audio cables

Security recommendations:

- Use trusted USB devices only
- Avoid unknown AIOC clones
- Disable unused USB ports where possible
- Do not expose the host system physically in public environments
- Use OS-level user permissions to restrict device access

Run ZPTTLink as a non-root user whenever possible.

---

## Host System Security

ZPTTLink depends on:

- BlueStacks (Android emulator)
- Windows or Linux host OS
- Virtual audio drivers
- USB serial drivers

Recommendations:

- Keep the OS fully updated
- Keep BlueStacks updated
- Use firewall rules to restrict inbound access
- Disable unnecessary services
- Do not expose development builds publicly

If deployed on a server:

- Use least-privilege user accounts
- Do not expose debug ports to the internet
- Avoid running with Administrator/root privileges

---

## Secrets & Configuration

If ZPTTLink uses:

- API keys
- MQTT credentials
- Webhooks
- Bot tokens

They must:

- Be stored in environment variables
- Not be hardcoded
- Not be committed to Git
- Not appear in logs

Use a `.env` file (excluded via `.gitignore`) when applicable.

---

## Audio Injection & Abuse Risks

Because ZPTTLink bridges digital voice to RF, potential abuse scenarios include:

- Remote audio injection
- RF spam transmission
- Unauthorized keying of transmitters
- Continuous carrier lock

Mitigation strategies:

- Add transmit timeout safeguards
- Implement PTT watchdog timers
- Log keying events
- Require explicit configuration to enable transmit mode
- Consider implementing an optional TX authorization layer

---

## Network Exposure

If ZPTTLink includes a web interface or API:

- Bind to localhost by default
- Require authentication for remote access
- Use HTTPS when exposed externally
- Avoid exposing control endpoints without authentication
- Rate-limit external API calls

Never expose control endpoints publicly without access control.

---

## Legal & Regulatory Notice

ZPTTLink users are responsible for:

- Complying with FCC regulations (USA) or local equivalents
- Following GMRS or Amateur radio rules
- Avoiding encryption where prohibited
- Proper station identification

The software does not enforce regulatory compliance automatically.

Use at your own risk.

---

## Supported Versions

Security updates are applied to:

- The latest tagged release
- The most recent minor version branch (if applicable)

Older versions may not receive patches.

---

## Secure Development Practices

ZPTTLink development guidelines:

- No hardcoded credentials
- No debug backdoors
- Review USB input handling carefully
- Validate serial input data
- Avoid arbitrary shell execution
- Sanitize user input

Pull Requests affecting security-sensitive components will receive additional review.

