#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

# Usage: ./trustyai-distribution/build.py

import shutil
import subprocess
import sys
from pathlib import Path

BASE_REQUIREMENTS = [
    "llama-stack==0.2.22",
]


def check_llama_installed():
    """Check if llama binary is installed and accessible."""
    if not shutil.which("llama"):
        print("Error: llama binary not found. Please install it first.")
        sys.exit(1)


def check_llama_stack_version():
    """Check if the llama-stack version in BASE_REQUIREMENTS matches the installed version."""
    try:
        result = subprocess.run(
            ["llama stack --version"],
            shell=True,
            capture_output=True,
            text=True,
            check=True,
        )
        installed_version = result.stdout.strip()

        # Extract version from BASE_REQUIREMENTS
        expected_version = None
        for req in BASE_REQUIREMENTS:
            if req.startswith("llama-stack=="):
                expected_version = req.split("==")[1]
                break

        if expected_version and installed_version != expected_version:
            print("Error: llama-stack version mismatch!")
            print(f"  Expected: {expected_version}")
            print(f"  Installed: {installed_version}")
            print(
                "  If you just bumped the llama-stack version in BASE_REQUIREMENTS, you must update the version from .pre-commit-config.yaml"
            )
            sys.exit(1)

    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not check llama-stack version: {e}")
        print("Continuing without version validation...")


def get_dependencies():
    """Execute the llama stack build command and capture dependencies."""
    cmd = "llama stack build --config trustyai-distribution/build.yaml --print-deps-only"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        # Categorize and sort different types of pip install commands
        standard_deps = []
        torch_deps = []
        no_deps = []
        no_cache = []

        for line in result.stdout.splitlines():
            if line.strip().startswith("uv pip"):
                # Split the line into command and packages
                parts = line.replace("uv ", "RUN ", 1).split(" ", 3)
                if len(parts) >= 4:  # We have packages to sort
                    cmd_parts = parts[:3]  # "RUN pip install"
                    packages = sorted(set(parts[3].split()))  # Sort the package names and remove duplicates

                    # Add quotes to packages with > or < to prevent bash redirection
                    packages = [
                        f"'{package}'"
                        if (">" in package or "<" in package)
                        else package
                        for package in packages
                    ]

                    # Modify pymilvus package to include milvus-lite extra
                    packages = [
                        package.replace("pymilvus", "pymilvus[milvus-lite]")
                        if "pymilvus" in package
                        else package
                        for package in packages
                    ]

                    # Determine command type and format accordingly
                    if ("--index-url" in line) or ("--extra-index-url" in line):
                        full_cmd = " ".join(cmd_parts + [" ".join(packages)])
                        torch_deps.append(full_cmd)
                    elif "--no-deps" in line:
                        full_cmd = " ".join(cmd_parts + [" ".join(packages)])
                        no_deps.append(full_cmd)
                    elif "--no-cache" in line:
                        full_cmd = " ".join(cmd_parts + [" ".join(packages)])
                        no_cache.append(full_cmd)
                    else:
                        formatted_packages = " \\\n    ".join(packages)
                        full_cmd = f"{' '.join(cmd_parts)} \\\n    {formatted_packages}"
                        standard_deps.append(full_cmd)
                else:
                    standard_deps.append(" ".join(parts))

        # Combine all dependencies in specific order
        all_deps = []
        all_deps.extend(sorted(standard_deps))  # Regular pip installs first
        all_deps.extend(sorted(torch_deps))  # PyTorch specific installs
        all_deps.extend(sorted(no_deps))  # No-deps installs
        all_deps.extend(sorted(no_cache))  # No-cache installs

        # TODO: Remove this once we have a stable PyPI index for trustyai_fms
        # Fix trustyai_fms package to use test PyPI index
        result = "\n".join(all_deps)
        result = result.replace(
            "llama_stack_provider_trustyai_fms==0.2.3",
            "--extra-index-url https://test.pypi.org/simple/ llama_stack_provider_trustyai_fms==0.2.3",
        )
        return result

    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        print(f"Command output: {e.output}")
        print(f"Command stderr: {e.stderr}")
        sys.exit(1)


def generate_containerfile(dependencies):
    """Generate Containerfile from template with dependencies."""
    template_path = Path("trustyai-distribution/Containerfile.in")
    output_path = Path("trustyai-distribution/Containerfile")

    if not template_path.exists():
        print(f"Error: Template file {template_path} not found")
        sys.exit(1)

    # Read template
    with open(template_path) as f:
        template_content = f.read()

    # Add warning message at the top
    warning = "# WARNING: This file is auto-generated. Do not modify it manually.\n# Generated by: trustyai-distribution/build.py\n\n"

    # Process template using string formatting
    containerfile_content = warning + template_content.format(dependencies=dependencies.rstrip())

    # Write output
    with open(output_path, "w") as f:
        f.write(containerfile_content)

    print(f"Successfully generated {output_path}")


def main():
    print("Checking llama installation...")
    check_llama_installed()

    print("Checking llama-stack version...")
    check_llama_stack_version()

    print("Getting dependencies...")
    dependencies = get_dependencies()

    print("Generating Containerfile...")
    generate_containerfile(dependencies)

    print("Done!")


if __name__ == "__main__":
    main()
