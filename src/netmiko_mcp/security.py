"""
Security validation and command verification layer for the Netmiko MCP server.

# How command verificaiton layer (should) work.

# 1. Default Deny
An empty allow/deny list denies everything. Nothing is permitted unless explicitly
added to the allow list (allowed_commands).

# 2. Deny Takes Precedence
If a command matches both the deny list and the allow list, it is denied. The deny
list always takes precedence over the allow list.

# 3. Allow List Does Not Cover Abbreviations
The allow list performs exact or glob matching only — it does not subsume
abbreviations. For example, allowed: ["show version"] does not
automatically permit "sh ver". LLMs and users are expected to send full,
un-abbreviated commands.

# 4. Deny List Covers All Abbreviations of the Same Word Count
A plain deny entry covers all abbreviated forms of the same word count.
For example, denied: ["show version"] denies "sh ver", "sho ver",
"show ver", etc. It does NOT deny a command with fewer words — "sh" alone
is not denied by denied: ["show version"]. It also does NOT deny commands
with more words. Denied: ["show ip interface"] does NOT block "show ip
interface brief". Use a glob entry to cover additional arguments
(see point 5).

# 5. Deny List Does Not Cover Additional Arguments by Default
A plain deny entry covers only commands with the exact same word count.
denied: ["show ip interface"] denies "sh ip int" but NOT "sh ip int brief".
To deny a command and its arguments, use a glob entry:
  - "show ip interface*"  — denies the base command and anything immediately
                              following with no space boundary.
  - "show ip interface *" — denies only invocations with at least one additional
                              argument; does NOT deny the base command alone.

# 6. Pipe Handling
The pipe character is disabled by default and must be explicitly enabled via
allow_pipe. When enabled:
  - Only the base command (before the pipe) is evaluated against allow/deny lists.
  - The pipe modifier must appear in the configured pipe_modifiers list.
  - Multiple pipes are always rejected.

# 7. Command Normalization and Allowed Characters
Commands are always normalized before validation:
  - All ASCII whitespace runs are collapsed to a single space; leading and
    trailing whitespace is stripped.
  - Only characters in allowed_command_chars are permitted. By default this
    excludes newline, carriage return, tab, and Unicode space lookalikes
    (NBSP, ideographic space, etc.).

# 8. Audit Logging
Every command attempt is logged with a specific reason: allowed, unsafe char,
deny match, pipe violation (multiple pipes or invalid modifier), or no allow
match.

# 9. Configuration Changes Have No Supported Tool
Currently there is no tool to support configuration changes. A future
Netmiko-MCP tool will support configuration changes. You should still be careful
NOT to allow any configuration commands via your allowed command list.

# 10. Glob Patterns
Glob patterns ("show *") are supported in both the allow and deny lists.

Allow list: glob patterns are converted to regular expressions internally.
Abbreviations are NOT expanded on the allow side — "show *" does not permit
"sh version".

Deny list: two trailing glob forms are supported, both cover abbreviated words:
  - "show ip interface*"  — the last word has an inline glob. Denies "show ip 
    interface" (including abbreviated forms), denies "show ip interfaces" (extra
    letter), denies "show ip interface brief" (extra word).
  - "show ip interface *" — the glob is a separate trailing word.
    At least one additional submitted word is required; the base command alone
    is NOT denied. denies "show ip interface brief" (including abbreviated forms),
    does NOT deny "show ip interface".

"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from netmiko.utilities import load_yaml_file

from netmiko_mcp.audit import (
    REASON_ALLOWED,
    REASON_DENY_MATCH,
    REASON_INVALID_PIPE_MODIFIER,
    REASON_MULTIPLE_PIPES,
    REASON_NO_ALLOW_MATCH,
    REASON_UNSAFE_CHAR,
)
from netmiko_mcp.config import settings

# Default fallback if no custom configuration is provided.
# We default to strictly denying everything. Users should provide a YAML
# configuration file to allow commands.
DEFAULT_ALLOWED_COMMANDS: list[str] = []
DEFAULT_DENIED_COMMANDS: list[str] = []


@dataclass
class ValidationResult:
    """The result of a validate_command call.

    allowed indicates whether the command should be permitted. reason is one
    of the REASON_* constants from the audit module and describes why the
    command was allowed or denied. The reason is intended to be recorded
    verbatim in the audit log.

    normalized_command holds the whitespace-normalized form of the submitted
    command. When allowed is True this is the exact string that should be
    forwarded to the network device.
    """

    allowed: bool
    reason: str
    normalized_command: str = ""


class TrieNode:
    """TrieNode in a character-level tree (prefix trie) for a single command
    word.

    children maps each character to the next TrieNode at this word level.

    word_end marks the end of a complete word for a deny entry.

    final_word marks the last word of a plain deny entry (no glob).

    glob_suffix marks the last word of an inline-glob deny entry (e.g.
      "interface*"). The submitted word may be a prefix of or extend beyond
      the stem, and extra submitted words are also permitted.

    glob_next_word marks the last word before a trailing space-glob (e.g.
      "interface *"). The submitted word must be a prefix of the stem only;
      at least one additional submitted word is required.

    next_word_trie is the root trie for the next word in a multi-word deny entry.
    """

    def __init__(self) -> None:
        self.children: dict[str, "TrieNode"] = {}
        self.word_end: bool = False
        self.final_word: bool = False
        self.glob_suffix: bool = False
        self.glob_next_word: bool = False
        self.next_word_trie: "TrieNode | None" = None


class AbbreviationDenyFilter:
    """Checks whether a submitted command is an abbreviation of any plain
    (non-glob) entry in the denied_commands list.

    Each deny entry is indexed in a hierarchy of character-level nodes (tries),
    one index per word. At each level the submitted word can match as a prefix of
    the deny word, so 'sh ver' can match 'show version'.

    A submitted command is denied if:
    - Every word of the deny entry is matched by the corresponding submitted word
      including prefixes (case-insensitive), AND
    - The submitted command has exactly the same number of words as the deny entry.

    Extra submitted words are NOT covered — 'sh ver sum' is NOT denied by
    'show version'. Use a glob deny entry ('show version *') to cover additional
    arguments.

    Abbreviated starting words are covered by all three forms, but word count
    rules still apply:
      - plain 'show ip interface'     denies 'sh ip int' (exact 3 words),
                                      but NOT 'sh ip int brief' (extra word).
      - inline-glob 'show ip interface*' denies both 'sh ip int' and
                                      'sh ip int brief'.
      - space-glob 'show ip interface *' denies 'sh ip int brief' (extra word
                                      satisfies the *), but NOT 'sh ip int' alone.

    Build once at load time via add(), then query per command via is_denied().
    """

    def __init__(self) -> None:
        self._root = TrieNode()

    def add(self, deny_entry: str) -> None:
        """Insert a deny entry (plain or trailing-glob) into the trie hierarchy.

        Supported forms:
          plain:        "show ip interface"   — exact word count match.
          inline glob:  "show ip interface*"  — last word stem + any suffix
                                                chars or extra words OK.
          space glob:   "show ip interface *" — prefix-only last word, requires
                                                at least one more submitted word.

        Entries with '*' in any non-trailing position are silently ignored.
        """
        words = deny_entry.strip().lower().split()
        if not words:
            return

        last = words[-1]

        if last == "*":
            # Space glob: e.g. "show ip interface *"
            prefix_words = words[:-1]
            if not prefix_words:
                return  # bare "*" — skip
            if any("*" in w for w in prefix_words):
                return  # glob in non-trailing position — unsupported
            is_inline_glob = False
            is_space_glob = True
            effective_words = prefix_words
        elif last.endswith("*"):
            # Inline glob: e.g. "show ip interface*"
            stem = last[:-1]
            if not stem:
                return  # degenerate — skip
            if any("*" in w for w in words[:-1]):
                return  # glob in non-trailing position — unsupported
            is_inline_glob = True
            is_space_glob = False
            effective_words = words[:-1] + [stem]
        else:
            # Plain entry: no glob
            if "*" in deny_entry:
                return  # '*' in unexpected position — unsupported
            is_inline_glob = False
            is_space_glob = False
            effective_words = words

        node = self._root
        for i, word in enumerate(effective_words):
            for char in word:
                if char not in node.children:
                    node.children[char] = TrieNode()
                node = node.children[char]
            node.word_end = True
            is_last = i == len(effective_words) - 1
            if is_last:
                if is_inline_glob:
                    node.glob_suffix = True
                elif is_space_glob:
                    node.glob_next_word = True
                else:
                    node.final_word = True
            else:
                if node.next_word_trie is None:
                    node.next_word_trie = TrieNode()
                node = node.next_word_trie

    def is_denied(self, submitted: str) -> bool:
        """Return True if submitted is an abbreviation of any deny entry.

        submitted should be the whitespace-normalized command string.
        Comparison is case-insensitive.
        """
        words = submitted.strip().lower().split()
        if not words:
            return False
        return self.match_word(trie_root=self._root, words=words, word_idx=0)

    def match_word(self, trie_root: TrieNode, words: list[str], word_idx: int) -> bool:
        """Traverse trie_root with words[word_idx]'s characters, then DFS for
        reachable terminal nodes and evaluate deny logic."""
        node = trie_root
        for char in words[word_idx]:
            if node.glob_suffix:
                # Submitted word extends past the deny stem — inline glob
                # covers the extra characters. Extra submitted words also OK.
                return True
            if char not in node.children:
                return False
            node = node.children[char]
        last_word = word_idx == len(words) - 1
        return self.find_word_end(
            node=node,
            words=words,
            word_idx=word_idx,
            last_word=last_word,
        )

    def find_word_end(
        self,
        node: TrieNode,
        words: list[str],
        word_idx: int,
        last_word: bool,
    ) -> bool:
        """DFS from node to find reachable is_terminal nodes and apply deny logic.

        The submitted word for word_idx ended somewhere inside the character trie.
        The submitted word may be a prefix of a longer deny word, so we DFS to
        find all complete deny words reachable from the current position.
        """
        if node.word_end:
            if node.final_word and last_word:
                # Plain entry: exact word count match — denied.
                return True
            if node.glob_suffix:
                # Inline glob: submitted word is a prefix of the deny stem.
                # Extra submitted words are also fine.
                return True
            if node.glob_next_word and not last_word:
                # Space glob: submitted word matched the deny stem (prefix or
                # exact) and at least one more submitted word exists.
                return True
            # Deny entry continues to the next word. Recurse if submitted has
            # another word.
            if not last_word and node.next_word_trie is not None:
                if self.match_word(
                    trie_root=node.next_word_trie, words=words, word_idx=word_idx + 1
                ):
                    return True
        # DFS into character children — the submitted word may be a shorter
        # prefix of a longer deny word.
        for child in node.children.values():
            if self.find_word_end(
                node=child,
                words=words,
                word_idx=word_idx,
                last_word=last_word,
            ):
                return True
        return False


def glob_to_regex(glob_pattern: str) -> re.Pattern[str]:
    """
    Convert a simple glob pattern containing '*' into a compiled regular expression.

    The wildcard '*' matches any character. Commands are validated against
    allowed_command_chars before reaching this function, so no additional
    wildcard restriction is needed here.

    A trailing ' *' (space then asterisk) is handled specially so that a pattern
    like 'show version *' matches both 'show version' and 'show version detail'.
    """
    escaped = re.escape(glob_pattern.strip())
    escaped = escaped.replace(r"\ \*", r"(?:\s+.*)?")
    escaped = escaped.replace(r"\*", r".*")

    return re.compile("^" + escaped + "$", re.IGNORECASE)


def deny_check(command: str, denied_commands: list[str]) -> bool:
    """Return True if the command matches any entry in denied_commands.

    Every entry is evaluated via glob_to_regex — the same logic as the allow
    check. A plain string (e.g. 'reload') matches only that exact command.
    A glob (e.g. 'reload *') matches any command starting with 'reload'.
    Denied always takes precedence over allowed.
    """
    for denied in denied_commands:
        if glob_to_regex(denied.strip()).match(command):
            return True
    return False


@lru_cache(maxsize=1)
def load_commands() -> dict[str, Any]:
    """
    Load the command whitelist/blacklist from the command_file defined in global config.
    Result is cached after the first call. A server restart is required to pick up
    changes to commands.yml.
    """
    file_path = Path(settings.command_file).expanduser()
    if file_path.is_file():
        return load_yaml_file(str(file_path))
    return {}


@lru_cache(maxsize=128)
def build_abbreviation_filter(denied_commands: tuple[str, ...]) -> AbbreviationDenyFilter:
    """Build and cache an AbbreviationDenyFilter from the denied_commands list.

    All deny entries are loaded into the trie — plain, inline-glob, and
    space-glob. The trie handles abbreviation matching for all forms so that
    abbreviated first words are caught. The regex path in deny_check() continues
    to handle exact and glob matches for fully-expanded commands.

    The cache is keyed on the denied_commands tuple so that different
    configurations get independent cached filters without requiring a server
    restart when tests supply different mock data.
    """
    deny_filter = AbbreviationDenyFilter()
    for entry in denied_commands:
        deny_filter.add(deny_entry=entry)
    return deny_filter


def validate_command(command: str) -> ValidationResult:
    """
    Validate that the requested command is safe to execute.

    Returns a ValidationResult with allowed=True and reason=REASON_ALLOWED if the
    command passes all checks, or allowed=False with a specific reason constant
    indicating why it was rejected. The reason is intended to be recorded in the
    audit log by the caller. normalized_command in the result is the whitespace-
    normalized form that should be forwarded to the network device when allowed.

    Rules applied in order:
    - Whitespace is normalized: all ASCII whitespace runs collapsed to a single
      space, leading/trailing whitespace stripped.
    - Command must contain only characters in allowed_command_chars (plus '|' when
      allow_pipe is True). Rejects Unicode space lookalikes and injection chars.
    - Command must NOT match any entry in denied_commands (checked against the
      base command before any pipe, supports glob patterns).
    - If a pipe is present, allow_pipe must be True, and the modifier must be in
      the configured pipe_modifiers list. Multiple pipes are always rejected.
    - Base command (before any pipe) must match an entry in allowed_commands.
    """
    commands = load_commands()

    allowed_commands = commands.get("allowed_commands", DEFAULT_ALLOWED_COMMANDS)
    denied_commands = commands.get("denied_commands", DEFAULT_DENIED_COMMANDS)

    # Normalize whitespace: collapse all ASCII whitespace runs (spaces, tabs,
    # vertical tabs, etc.) to a single space and strip leading/trailing
    # whitespace. This is the form forwarded to the network device on success.
    normalized = " ".join(command.split())

    # Allowlist check: reject any character not in the effective allowed set.
    # The pipe character is added automatically when allow_pipe is True.
    # This catches Unicode space lookalikes (NBSP, ideographic space, etc.)
    # and injection characters that survive whitespace normalization.
    effective_allowed = set(settings.allowed_command_chars)
    if settings.allow_pipe:
        effective_allowed.add("|")
    if any(c not in effective_allowed for c in normalized):
        return ValidationResult(
            allowed=False, reason=REASON_UNSAFE_CHAR, normalized_command=normalized
        )

    # Extract base command and potential pipe segment.
    parts = normalized.split("|", 1)
    base_command = parts[0].strip()

    # Deny check runs against base_command (after pipe split) so that a denied
    # command cannot bypass the check by appending a pipe modifier.
    # Two paths are run:
    #   1. deny_check() — regex/glob path, catches exact and glob deny entries.
    #   2. build_abbreviation_filter() — trie path, catches abbreviated forms of
    #      plain deny entries (e.g. "sh ver" denied by "show version").
    if deny_check(command=base_command, denied_commands=denied_commands):
        return ValidationResult(
            allowed=False, reason=REASON_DENY_MATCH, normalized_command=normalized
        )
    if build_abbreviation_filter(denied_commands=tuple(denied_commands)).is_denied(
        submitted=base_command
    ):
        return ValidationResult(
            allowed=False, reason=REASON_DENY_MATCH, normalized_command=normalized
        )

    # Pipe check: validate if a pipe exists. When allow_pipe is False, the
    # pipe character never reaches this point — it is rejected by the allowlist
    # check above since '|' is only added to effective_allowed when allow_pipe
    # is True.
    if len(parts) > 1:
        pipe_modifier = parts[1].strip().lower()

        # Multiple pipes are never allowed.
        if "|" in pipe_modifier:
            return ValidationResult(
                allowed=False, reason=REASON_MULTIPLE_PIPES, normalized_command=normalized
            )

        if pipe_modifier:
            modifier_keyword = pipe_modifier.split()[0]
            if modifier_keyword not in settings.pipe_modifiers:
                return ValidationResult(
                    allowed=False,
                    reason=REASON_INVALID_PIPE_MODIFIER,
                    normalized_command=normalized,
                )
        else:
            return ValidationResult(
                allowed=False, reason=REASON_INVALID_PIPE_MODIFIER, normalized_command=normalized
            )

    # Test base command against the allowed_commands list.
    for allowed in allowed_commands:
        if "*" in allowed:
            pattern = glob_to_regex(allowed)
            if pattern.match(base_command):
                return ValidationResult(
                    allowed=True, reason=REASON_ALLOWED, normalized_command=normalized
                )
        elif base_command.lower() == allowed.strip().lower():
            return ValidationResult(
                allowed=True, reason=REASON_ALLOWED, normalized_command=normalized
            )

    # If it matches no allowed entry, deny it.
    return ValidationResult(
        allowed=False, reason=REASON_NO_ALLOW_MATCH, normalized_command=normalized
    )
