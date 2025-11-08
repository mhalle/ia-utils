"""Clean logging utilities for ia-utils."""

import sys
from typing import Optional
import click


class Logger:
    """Simple logger that wraps click.echo for clean error/info handling."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def info(self, message: str, nl: bool = True) -> None:
        """Log info message (always shown)."""
        click.echo(message, nl=nl)

    def verbose_info(self, message: str, nl: bool = True) -> None:
        """Log verbose info message (only shown if verbose=True)."""
        if self.verbose:
            click.echo(message, nl=nl)

    def error(self, message: str) -> None:
        """Log error message to stderr."""
        click.echo(f"Error: {message}", err=True)

    def warning(self, message: str) -> None:
        """Log warning message to stderr."""
        click.echo(f"Warning: {message}", err=True)

    def success(self, message: str) -> None:
        """Log success message."""
        click.echo(message)

    def section(self, title: str) -> None:
        """Print a section header."""
        click.echo(f"\n{title}")
        click.echo("=" * 70)

    def subsection(self, title: str) -> None:
        """Print a subsection header."""
        click.echo(f"\n{title}")

    def progress(self, message: str, nl: bool = False) -> None:
        """Print progress indicator without newline (only in verbose mode)."""
        if self.verbose:
            click.echo(message, nl=nl)

    def progress_done(self, message: str = "✓") -> None:
        """Complete a progress indicator (only in verbose mode)."""
        if self.verbose:
            click.echo(f" {message}")

    def progress_fail(self, message: str = "✗") -> None:
        """Fail a progress indicator (only in verbose mode)."""
        if self.verbose:
            click.echo(f" {message}", err=True)


def get_logger(verbose: bool = False) -> Logger:
    """Get a logger instance."""
    return Logger(verbose=verbose)
