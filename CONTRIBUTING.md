# Contributing to ZPTTLink

Thank you for your interest in contributing to ZPTTLink!  
We welcome contributions from the community and want to make the process easy and transparent.

---

## Ways to Contribute

- Submit bug reports and feature requests through GitHub Issues
- Improve documentation (README, comments, etc.)
- Submit Pull Requests (PRs) to fix bugs or add features
- Help with testing on different platforms (Windows, macOS, Linux)
- Share ideas and feedback to improve usability

---

## Code Style

- Write clear, readable Python code (PEP8 preferred)
- Add comments where necessary
- Include docstrings for functions and classes
- Keep it simple (KISS principle) unless complexity is required

---

## Pull Request Guidelines

1. Fork the repository  
2. Create a new branch for your feature or bugfix  
   ```bash
   git checkout -b feature/my-feature
   ```
3. Commit changes with clear, descriptive messages  
   ```bash
   git commit -m "Add serial port auto-detection"
   ```
4. Push to your fork  
   ```bash
   git push origin feature/my-feature
   ```
5. Open a Pull Request on GitHub and describe your changes

---

## Testing

Before submitting, please test your changes:

- Verify the program runs without errors:
  ```bash
  python -m zpttlink --list-serial
  ```
- Ensure your changes do not break existing functionality
- Test on at least one supported OS (Windows, macOS, Linux)

---

## Suggestions & Issues

- Use GitHub Issues for bug reports, feature requests, or questions
- When filing an issue, include:
  - OS/platform (Windows/macOS/Linux)
  - Python version
  - Steps to reproduce the problem
  - Expected vs. actual behavior

---

## Licensing Notes

By contributing to ZPTTLink, you agree that your contributions will be licensed under the MIT License.

ZPTTLink is an independent, open-source project that interacts with or utilizes the following third-party software and platforms:

- Zello is a proprietary software by Zello Inc.
- BlueStacks is an Android emulator by BlueStacks Inc.
- Waydroid is an Android container for Linux developed by the Waydroid Project.
- Android is a mobile operating system developed by Google LLC.

---

## Acknowledgments

Thanks to all contributors, testers, and the open-source community that makes projects like this possible.  
We look forward to your contributions.
