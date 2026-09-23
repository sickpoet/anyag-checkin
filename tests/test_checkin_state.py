import re
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import checkin
from checkin import (
	AUTO_CHECKED_WITH_GAIN_LABEL,
	STATUS_ALREADY_CHECKED,
	STATUS_AUTO_CHECKED,
	STATUS_CHECKED_IN,
	STATUS_FAILED,
	CheckInOutcome,
	compute_day_gain,
	generate_balance_hash,
	resolve_baseline,
	resolve_outcome_label,
)

# --- 余额 hash（原有） ------------------------------------------------------------


def test_balance_hash_changes_when_quota_changes():
	before = {'account_1': {'quota': 100.0, 'used': 20.0}}
	after = {'account_1': {'quota': 125.0, 'used': 20.0}}

	assert generate_balance_hash(before) != generate_balance_hash(after)


def test_balance_hash_changes_when_used_quota_changes():
	before = {'account_1': {'quota': 100.0, 'used': 20.0}}
	after = {'account_1': {'quota': 100.0, 'used': 21.0}}

	assert generate_balance_hash(before) != generate_balance_hash(after)


def test_balance_hash_is_stable_for_equivalent_balances():
	left = {
		'account_2': {'quota': 50.0, 'used': 1.0},
		'account_1': {'quota': 100.0, 'used': 20.0},
	}
	right = {
		'account_1': {'used': 20.0, 'quota': 100.0},
		'account_2': {'used': 1.0, 'quota': 50.0},
	}

	assert generate_balance_hash(left) == generate_balance_hash(right)


# --- 签到日 current_day ------------------------------------------------------------


def test_current_day_returns_iso_date(monkeypatch):
	monkeypatch.setenv('CHECKIN_TZ_OFFSET', '8')

	assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', checkin.current_day())


def test_current_day_tolerates_invalid_offset(monkeypatch):
	monkeypatch.setenv('CHECKIN_TZ_OFFSET', 'nonsense')

	assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', checkin.current_day())


def test_current_day_offset_ordering(monkeypatch):
	"""UTC-12 的日期不可能晚于 UTC+14 的日期（跨度 26 小时）。"""
	monkeypatch.setenv('CHECKIN_TZ_OFFSET', '-12')
	west = checkin.current_day()
	monkeypatch.setenv('CHECKIN_TZ_OFFSET', '14')
	east = checkin.current_day()

	assert west <= east


# --- 基准解析 resolve_baseline -----------------------------------------------------


def test_resolve_baseline_without_state():
	assert resolve_baseline(None, '2026-09-23') == (None, None)
	assert resolve_baseline({}, '2026-09-23') == (None, None)


def test_resolve_baseline_same_day_keeps_established_baseline():
	"""同一天内必须沿用已建立的基准，否则"今日累计"会被后续运行冲掉。"""
	stored = {
		'day': '2026-09-23',
		'baseline_total': 1000.0,
		'baseline_day': '2026-09-22',
		'last_total': 1025.0,
	}

	assert resolve_baseline(stored, '2026-09-23') == (1000.0, '2026-09-22')


def test_resolve_baseline_new_day_uses_previous_close():
	"""跨天时用上一次观测值（前一天的收尾总量）作为新基准。"""
	stored = {
		'day': '2026-09-22',
		'baseline_total': 975.0,
		'baseline_day': '2026-09-21',
		'last_total': 1000.0,
	}

	assert resolve_baseline(stored, '2026-09-23') == (1000.0, '2026-09-22')


# --- 日增量 compute_day_gain -------------------------------------------------------


def test_compute_day_gain():
	assert compute_day_gain(1075.0, 1050.0) == 25.0
	assert compute_day_gain(1000.0, 1000.0) == 0.0


def test_compute_day_gain_is_neutral_to_consumption():
	"""消费让余额下降、累计消耗上升，总量不变 —— 所以日增量必须是 0。"""
	quota_before, used_before = 540.45, 1834.55
	consumed = 47.07
	quota_after = quota_before - consumed
	used_after = used_before + consumed

	total_before = quota_before + used_before
	total_after = quota_after + used_after

	assert total_after == total_before
	assert compute_day_gain(total_after, total_before) == 0.0


def test_compute_day_gain_without_baseline():
	assert compute_day_gain(1075.0, None) is None
	assert compute_day_gain(None, 1050.0) is None


def test_compute_day_gain_can_be_negative():
	"""平台若重置累计消耗，总量会倒退，如实反映而不是藏起来。"""
	assert compute_day_gain(900.0, 1000.0) == -100.0


# --- 标签升级 resolve_outcome_label ------------------------------------------------


def test_auto_label_upgraded_when_total_grew():
	"""agentrouter 拿到"总量增加"这个实证后，不再只说"未获接口确认"。"""
	label = resolve_outcome_label(CheckInOutcome(STATUS_AUTO_CHECKED), 25.0)

	assert label == AUTO_CHECKED_WITH_GAIN_LABEL
	assert '总量已增加' in label
	assert '未获接口确认' not in label


def test_auto_label_kept_when_no_gain_or_no_baseline():
	kept = CheckInOutcome(STATUS_AUTO_CHECKED).label

	assert resolve_outcome_label(CheckInOutcome(STATUS_AUTO_CHECKED), 0.0) == kept
	assert resolve_outcome_label(CheckInOutcome(STATUS_AUTO_CHECKED), None) == kept
	assert resolve_outcome_label(CheckInOutcome(STATUS_AUTO_CHECKED), -1.0) == kept


def test_gain_does_not_override_server_confirmed_labels():
	"""已被服务端确认的状态不需要推断，标签保持原样。"""
	for status in (STATUS_CHECKED_IN, STATUS_ALREADY_CHECKED, STATUS_FAILED):
		outcome = CheckInOutcome(status)
		assert resolve_outcome_label(outcome, 25.0) == outcome.label


# --- 状态文件读写 ------------------------------------------------------------------


def test_state_round_trip(monkeypatch, tmp_path):
	state_file = tmp_path / 'checkin_state.json'
	monkeypatch.setattr(checkin, 'CHECKIN_STATE_FILE', str(state_file))

	assert checkin.load_checkin_state() == {}

	accounts = {
		'any主帐号': {
			'day': '2026-09-23',
			'baseline_total': 1000.0,
			'baseline_day': '2026-09-22',
			'last_total': 1025.0,
		}
	}
	checkin.save_checkin_state(accounts)

	assert checkin.load_checkin_state() == accounts


def test_state_load_tolerates_corrupt_file(monkeypatch, tmp_path):
	state_file = tmp_path / 'checkin_state.json'
	state_file.write_text('{not json', encoding='utf-8')
	monkeypatch.setattr(checkin, 'CHECKIN_STATE_FILE', str(state_file))

	assert checkin.load_checkin_state() == {}


def test_state_load_tolerates_unexpected_shape(monkeypatch, tmp_path):
	state_file = tmp_path / 'checkin_state.json'
	state_file.write_text('[1, 2, 3]', encoding='utf-8')
	monkeypatch.setattr(checkin, 'CHECKIN_STATE_FILE', str(state_file))

	assert checkin.load_checkin_state() == {}
