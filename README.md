# RADPS Roadmap

This repository is used to track high-level roadmap items — features, enhancements, and cross-cutting work — across the **Radio Astronomy Data Processing System (RADPS)** project. It acts as a single, central place to view and discuss planned work that may span multiple repositories.

## What is RADPS?

RADPS (Radio Astronomy Data Processing System) is a collection of packages being developed to support next-generation radio telescope data processing for facilities such as the [ngVLA](https://ngvla.nrao.edu/) and [ALMA WSU](https://science.nrao.edu/facilities/alma/science_sustainability/wideband-sensitivity-upgrade).

## Repositories in the RADPS Ecosystem

| Repository | Description |
|---|---|
| [RADPS](https://github.com/casangi/RADPS) | Core RADPS infrastructure (workflows, cluster deployment) |
| [xradio](https://github.com/casangi/xradio) | Xarray radio astronomy data I/O |
| [astroviper](https://github.com/casangi/astroviper) | Radio interferometry data processing |
| [toolviper](https://github.com/casangi/toolviper) | Tools and utilities for optimized radio astronomy processing |
| [graphviper](https://github.com/casangi/graphviper) | Dask-based MapReduce for multi-Xarray datasets |
| [calviper](https://github.com/casangi/calviper) | Calibration |
| [cloudviper](https://github.com/casangi/cloudviper) | Cloud-native container orchestration system configurations |
| [testviper](https://github.com/casangi/testviper) | Automated test repository for the VIPER ecosystem |
| [benchviper](https://github.com/casangi/benchviper) | Performance monitoring for the VIPER ecosystem |
| [pyasdm](https://github.com/casangi/pyasdm) | ASDM backend for the VIPER framework |
| [cubevis](https://github.com/casangi/cubevis) | Visualization tools for CASA images |
| [vidavis](https://github.com/casangi/vidavis) | Visibility data visualization |
| [radpsdocs](https://github.com/casangi/radpsdocs) | RADPS-related documentation |
| [radps-context](https://github.com/casangi/radps-context) | RADPS context work |

## How to Use This Repository

### Submitting a Roadmap Item

Use the [issue templates](.github/ISSUE_TEMPLATE/) to submit new roadmap items:

- **Feature Request** — propose a new capability or enhancement that may affect one or more repositories.
- **Epic** — describe a large body of work composed of multiple related features or tasks.
- **Cross-Repository Bug** — report a defect whose root cause or fix spans multiple repositories.

When filing an issue, please:
1. Use the appropriate template for your issue type.
2. Clearly describe which repository or repositories are affected.
3. Add relevant labels (e.g., the affected repo name, priority, or theme).
4. Link to any related issues in individual repositories using GitHub's `#` reference syntax or full URLs.

### Labels

Issues in this repository use labels to organize work. Common labels include:

| Label | Description |
|---|---|
| `feature` | A new capability or enhancement |
| `epic` | A large body of related work |
| `bug` | A defect spanning multiple repositories |
| `infrastructure` | Work related to build, CI, deployment, or tooling |
| `documentation` | Documentation improvements |
| `high-priority` | Items that are urgent or blocking |
| `needs-discussion` | Items that require further design or scoping before work begins |

### Tracking Progress

Roadmap issues are discussed and tracked here, while the actual implementation work happens in individual repository issues. Link roadmap issues to implementation issues using the **Development** sidebar or by mentioning the issue URL in a comment.
