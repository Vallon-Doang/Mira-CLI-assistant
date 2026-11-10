from __future__ import annotations

from mira.execution import (
    RISK_DESTRUCTIVE,
    RISK_MODERATE,
    RISK_SAFE,
    STATUS_EXECUTED,
    STATUS_SPAWN_FAILED,
    classify,
    detect_shell_features,
    execute_plan,
    extract_command,
)


def test_extract_command_marker() -> None:
    cleaned, command, issue = extract_command("Check this.\nCOMMAND: df -h\n")
    assert cleaned == "Check this."
    assert command == "df -h"
    assert issue is None


def test_extract_command_fenced_block() -> None:
    cleaned, command, issue = extract_command("Use:\n```bash\ndf -h\n```\n")
    assert cleaned == "Use:"
    assert command == "df -h"
    assert issue is None


def test_extract_command_rejects_multiple() -> None:
    cleaned, command, issue = extract_command("COMMAND: ls\nCOMMAND: df -h\n")
    assert cleaned == "COMMAND: ls\nCOMMAND: df -h\n"
    assert command is None
    assert issue and "multiple" in issue


def test_extract_command_none() -> None:
    cleaned, command, issue = extract_command("Just an answer.")
    assert cleaned == "Just an answer."
    assert command is None
    assert issue is None


def test_extract_bare_first_line_command() -> None:
    cleaned, command, issue = extract_command(
        "df -h\nThis command displays disk usage."
    )
    assert cleaned == "This command displays disk usage."
    assert command == "df -h"
    assert issue is None


def test_extract_does_not_treat_prose_as_command() -> None:
    cleaned, command, issue = extract_command(
        "Use `df -h` to check disk usage."
    )
    assert cleaned == "Use `df -h` to check disk usage."
    assert command is None
    assert issue is None


def test_extract_does_not_treat_later_code_as_command() -> None:
    cleaned, command, issue = extract_command(
        "Here is the command:\ndf -h"
    )
    assert cleaned == "Here is the command:\ndf -h"
    assert command is None
    assert issue is None


def test_classify_safe_read_only() -> None:
    plan = classify("df -h")
    assert plan.risk == RISK_SAFE
    assert plan.auto_run is True
    assert plan.shell is False


def test_classify_git_status_is_safe() -> None:
    assert classify("git status").risk == RISK_SAFE


def test_classify_git_reset_is_destructive() -> None:
    assert classify("git reset --hard").risk == RISK_DESTRUCTIVE


def test_classify_systemctl_restart_is_moderate() -> None:
    plan = classify("systemctl restart sshd")
    assert plan.risk == RISK_MODERATE
    assert plan.auto_run is False


def test_classify_rm_is_destructive() -> None:
    assert classify("rm -rf /tmp/example").risk == RISK_DESTRUCTIVE


def test_classify_sudo_is_destructive() -> None:
    assert classify("sudo systemctl status sshd").risk == RISK_DESTRUCTIVE


def test_classify_pipe_is_shell_and_moderate() -> None:
    plan = classify("df -h | sort")
    assert plan.shell is True
    assert plan.risk == RISK_MODERATE
    assert "pipe" in plan.shell_features


def test_classify_quoted_glob_is_not_shell() -> None:
    plan = classify("find . -name '*.py'")
    assert plan.shell is False
    assert plan.risk == RISK_SAFE


def test_classify_command_substitution_is_destructive() -> None:
    assert classify("echo $(whoami)").risk == RISK_DESTRUCTIVE


def test_classify_git_tag_creation_is_moderate() -> None:
    assert classify("git tag v1").risk == RISK_MODERATE
    assert classify("git tag -l 'v*'").risk == RISK_SAFE


def test_classify_unknown_git_subcommand_needs_confirmation() -> None:
    assert classify("git frobnicate").risk == RISK_MODERATE


def test_classify_systemctl_option_query_is_safe() -> None:
    assert classify("systemctl --failed").risk == RISK_SAFE
    assert classify("systemctl frobnicate").risk == RISK_MODERATE


def test_classify_unknown_container_subcommand_needs_confirmation() -> None:
    assert classify("docker compose up").risk == RISK_MODERATE
    assert classify("docker ps").risk == RISK_SAFE


def test_classify_ip_monitor_is_moderate() -> None:
    assert classify("ip monitor").risk == RISK_MODERATE


def test_classify_ip_netns_exec_is_destructive() -> None:
    assert classify("ip netns exec demo bash").risk == RISK_DESTRUCTIVE


def test_classify_firewall_state_change_is_moderate() -> None:
    assert classify("firewall-cmd --runtime-to-permanent").risk == RISK_MODERATE
    assert classify("firewall-cmd --list-all").risk == RISK_SAFE


def test_classify_npm_audit_fix_is_moderate() -> None:
    assert classify("npm audit fix").risk == RISK_MODERATE
    assert classify("npm audit").risk == RISK_SAFE


def test_classify_dnf_group_remove_is_destructive() -> None:
    assert classify("dnf group remove web-server").risk == RISK_DESTRUCTIVE


def test_detect_shell_features_ignores_quoted_metacharacters() -> None:
    assert detect_shell_features("printf 'a|b'") == []


def test_execute_simple_command() -> None:
    result = execute_plan(classify("printf hello"))
    assert result.status == STATUS_EXECUTED
    assert result.executed is True
    assert result.exit_code == 0
    assert result.stdout == "hello"


def test_execute_shell_pipeline() -> None:
    result = execute_plan(classify("printf 'a\\nb\\n' | wc -l"))
    assert result.executed is True
    assert result.exit_code == 0
    assert result.stdout.strip() == "2"


def test_execute_nonzero_exit() -> None:
    result = execute_plan(classify("sh -c 'exit 7'"))
    assert result.executed is True
    assert result.exit_code == 7


def test_execute_timeout_kills_process() -> None:
    result = execute_plan(classify("sleep 5"), timeout=0.2)
    assert result.timed_out is True
    assert result.executed is True
    assert result.duration_ms is not None


def test_execute_truncates_output() -> None:
    result = execute_plan(classify("printf 'abcdefghij'"), max_output=4)
    assert result.truncated is True
    assert result.stdout.startswith("abcd")
    assert "truncated" in result.stdout


def test_execute_missing_binary() -> None:
    result = execute_plan(classify("definitely-not-a-real-command-xyz"))
    assert result.status == STATUS_SPAWN_FAILED
    assert result.executed is False
    assert result.exit_code == 127


def test_classify_tail_follow_is_moderate() -> None:
    assert classify("tail -f /var/log/messages").risk == RISK_MODERATE
    assert classify("tail -n 20 /var/log/messages").risk == RISK_SAFE


def test_classify_journalctl_follow_is_moderate() -> None:
    assert classify("journalctl -u sshd -f").risk == RISK_MODERATE
    assert classify("journalctl -u sshd").risk == RISK_SAFE


def test_classify_journalctl_vacuum_is_destructive() -> None:
    assert classify("journalctl --vacuum-size=100M").risk == RISK_DESTRUCTIVE


def test_classify_dmesg_follow_is_moderate() -> None:
    assert classify("dmesg -w").risk == RISK_MODERATE
    assert classify("dmesg").risk == RISK_SAFE


def test_classify_dmesg_clear_is_destructive() -> None:
    assert classify("dmesg -C").risk == RISK_DESTRUCTIVE


def test_classify_container_logs_follow_is_moderate() -> None:
    assert classify("docker logs -f demo").risk == RISK_MODERATE
    assert classify("podman logs --follow demo").risk == RISK_MODERATE
    assert classify("docker logs demo").risk == RISK_SAFE
