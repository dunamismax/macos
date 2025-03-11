# ----------------------------------------------------------------------------

rewrite (Claude 3.7 Sonnet)
using new prompt / template

------------------------------------------------------------------------------

```
└── 📁_scripts
    *└── _template.md
    *└── _to-to.md
    └── deploy_scripts.py
    └── fail2ban_toolkit.py
    └── fedora_package_installer.py
    └── ffmpeg_converter_toolkit.py
    └── file_toolkit.py
    └── fix_ssh_tool.py
    └── hacker_toolkit.py
    └── hacking_tools.py
    └── hello_world.py
    └── high_dpi_scaling_x11.py
    └── log_monitor.py
    └── metasploit.py
    └── network_toolkit.py
    └── popos_wayland_setup.py
    └── python_dev_setup.py
    └── reset_tailscale.py
    └── secure_disk_eraser.py
    └── sftp_toolkit.py
    └── ssh_machine_selector.py
    └── system_monitor.py
    └── ubuntu_voip_setup.py
    └── unified_backup_restore_deployment.py
    └── unified_backup.py
    └── unified_restore_to_home.py
    └── universal_downloader.py
    └── update_dns_records.py
    └── update_plex.py
    └── virtualization_setup.py
    └── vm_manager.py
    └── vscode_wayland_setup.py
    └── zfs_setup.py
```

---------------------------------------------------------------------------------------------

Prompt 1 (Interactive CLI):
Create an interactive terminal application following the Advanced Terminal Application Generator standards. The application must include:

Professional UI with the Nord color theme palette consistently applied to all interface elements.
Interactive, menu-driven interface with numbered options, validation, and intuitive navigation.
Dynamic ASCII banner headers using Pyfiglet with frost gradient coloring that adapts to terminal width.
Rich library integration for panels, tables, spinners, and real-time progress tracking of operations.
Comprehensive error handling with color-coded messaging (green for success, yellow for warnings, red for errors).
Signal handlers for SIGINT and SIGTERM to ensure graceful application termination.
Type annotations for all function signatures and dataclasses for structured data.
Standardized section structure following the exact order: dependencies, configuration, Nord colors, data structures, UI helpers, core functionality, signal handling, interactive menu, and entry point.

Build the application with a production-grade user experience focusing on responsiveness, error recovery, and visual consistency. The application must work on Ubuntu without modification and should not use argparse or implement command-line arguments.

---------------------------------------------------------------------------------------------

Prompt 2 (Unattended/Automated Script):
Create an automated terminal application that adheres to the Advanced Terminal Application Generator standards. This application must:

Execute autonomously with professional terminal output using the Nord color theme.
Display a dynamic ASCII banner with Pyfiglet and frost gradient styling at startup and for each major operational phase.
Integrate the Rich library for visual feedback, including:

Progress bars with spinners for long-running operations
Panels with appropriate titles for information sections
Color-coded status messaging (green for success, yellow for warnings, red for errors)


Implement robust error handling with try/except blocks around all external operations and file I/O.
Include signal handlers for SIGINT and SIGTERM to perform appropriate cleanup on termination.
Follow the standardized structure with clearly demarcated sections using delimiter comments.
Ensure proper resource management with cleanup operations that run even during abnormal termination.

The application should operate without user interaction while providing clear, real-time visual feedback on its progress and status. It must work on Ubuntu without modification and should not use argparse or implement command-line arguments.

---------------------------------------------------------------------------------------------

rewrite (claude 3.7 sonnet)
using new prompt

---------------------------------------------------------------------------------------------

Below is an essential cheat sheet for using Nala. It distills the key commands and options you need to know:

# Nala Command Cheat Sheet

## Installation: `nala install`

- **Basic Usage:**  

  ```bash
  nala install [--options] <pkg1> <pkg2> ...
  ```

- **Examples:**
  - Install multiple packages:  
    `nala install package1 package2`
  - Install a specific version:  
    `nala install tmux=3.3a-3~bpo11+1`
  - Install from a URL:  
    `nala install https://example.org/path/to/pkg.deb`
- **Common Options:**
  - **Transaction Behavior:**  
    - `--purge` — Purge removed packages.
    - `-d, --download-only` — Only download packages without unpacking.
    - `-t, --target-release <release>` — Specify release (e.g., `testing`).
    - `--remove-essential` — Allow removal of essential packages.
  - **Prompts & Summary:**  
    - `-y, --assume-yes` / `-n, --assume-no` — Automatic yes/no for prompts.
    - `--simple` / `--no-simple` — Choose between condensed or detailed summary.
  - **Additional Options:**  
    - `-o, --option <option>` — Pass extra options to apt/nala/dpkg.
    - `-v, --verbose` — Display extra debugging info.
    - `--autoremove` / `--no-autoremove` — Enable/disable automatic removal of unneeded packages.
    - `--update` / `--no-update` — Update package lists before running (default for upgrade).
    - `--install-recommends` / `--no-install-recommends` — Toggle installation of recommended packages.
    - `--install-suggests` / `--no-install-suggests` — Toggle installation of suggested packages.
    - `--fix-broken` / `--no-fix-broken` — Attempt to fix broken dependencies.
    - `--debug` and `--raw-dpkg` — For troubleshooting and raw dpkg output.

## Update: `nala update`

- **Usage:**  

  ```bash
  nala update [--options]
  ```

- **Description:**  
  Updates the package list (similar to `apt update`).
- **Key Options:**  
  - `--debug`, `--raw-dpkg`, `-o, --option`, `-v, --verbose`, `-h, --help`

## Upgrade: `nala upgrade`

- **Usage:**  

  ```bash
  nala upgrade [--options]
  ```

- **Modes:**
  - **Standard Upgrade:** Only upgrades packages and autoremoves unneeded ones.
  - **Full Upgrade:**  

    ```bash
    nala upgrade --full
    ```  

    (Aliases: `nala full-upgrade`, `nala dist-upgrade`) — Upgrades, installs new packages, and removes packages if necessary.
- **Additional Options:**  
  - `--exclude <pkg>` — Exclude specific packages (multiple allowed).
  - Others are similar to `nala install`: options like `--purge`, `-d/--download-only`, `-y/--assume-yes`, `--autoremove`, `--update`, etc.

## Search: `nala search`

- **Usage:**  

  ```bash
  nala search [--options] <pattern>
  ```

- **Description:**  
  Searches package names and descriptions using regex (default) or glob patterns.
- **Examples:**
  - Regex search:  
    `nala search "nala"`
  - Glob search (prefix with `g/`):  
    `nala search "g/nala*"`
- **Key Options:**  
  - `--full` — Show full package descriptions.
  - `-n, --names` — Search only in package names.
  - `-i, --installed` — List only installed packages.
  - `-N, --nala-installed` — List packages explicitly installed with Nala.
  - `-u, --upgradable` — List only upgradable packages.
  - `-a, --all-versions` — Show all versions.
  - `-A, --all-arches` — List all architectures.
  - `-V, --virtual` — Show only virtual packages.
  - Also supports `--debug`, `-v, --verbose`, and `-h, --help`.

## Fetch Mirrors: `nala fetch`

- **Usage:**  

  ```bash
  nala fetch [--options]
  ```

- **Description:**  
  Retrieves fast mirrors to speed up downloads by parsing mirror lists (from Debian, Ubuntu, or Devuan).
- **Key Options:**
  - `--debian <release>`, `--ubuntu <release>`, `--devuan <release>` — Specify the distro/release.
  - `--https-only` — Only list HTTPS mirrors.
  - `--auto` — Run non-interactively.
  - `--fetches <number>` — Number of mirrors to display for selection.
  - `--sources` — Include source repositories.
  - `--non-free` — Add contrib and non-free (Debian only).
  - `-c, --country <code>` — Filter by country (repeatable for multiple codes).
  - Additional options: `--debug`, `-v, --verbose`, `-h, --help`.

## Autoremove/Autopurge: `nala autoremove` / `nala autopurge`

- **Usage:**  

  ```bash
  nala autoremove [--options]
  ```

  or  

  ```bash
  nala autopurge [--options]  # equivalent to: nala autoremove --purge
  ```

- **Description:**  
  Removes packages (usually orphaned dependencies) that are no longer needed.
- **Key Options:**
  - `--config` — Purge configuration files for removed packages.
  - `--purge` — Purge packages rather than just removing them.
  - Plus standard options: `--debug`, `--raw-dpkg`, `-d, --download-only`, `-y, --assume-yes`, `--simple`, `-o, --option`, etc.

## Clean: `nala clean`

- **Usage:**  

  ```bash
  nala clean [--options]
  ```

- **Description:**  
  Clears local caches:
  - Removes downloaded package files (typically in `/var/cache/apt/archives`).
  - Deletes package cache files (`pkgcache.bin` and `srcpkgcache.bin`).
- **Key Options:**
  - `--lists` — Also remove package lists (from `/var/lib/apt/lists`).
  - `--fetch` — Remove the `nala-sources.list` file created by `nala fetch`.
  - Additional options: `--debug`, `-v, --verbose`, `-h, --help`.
