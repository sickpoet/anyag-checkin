from checkin import (
	STATUS_ALREADY_CHECKED,
	STATUS_AUTO_CHECKED,
	STATUS_CHECKED_IN,
	STATUS_FAILED,
	CheckInOutcome,
	format_account_line,
	format_delta,
	short_day,
)

# --- 标签 --------------------------------------------------------------------------


def test_labels_distinguish_each_status():
	labels = {
		STATUS_CHECKED_IN: '✅ 签到成功',
		STATUS_ALREADY_CHECKED: '✅ 今日已签到',
		STATUS_AUTO_CHECKED: '✅ 自动签到',
		STATUS_FAILED: '❌ 签到失败',
	}
	for status, expected in labels.items():
		assert CheckInOutcome(status).label == expected

	assert len(set(labels.values())) == 4


def test_labels_stay_short_enough_for_one_line():
	"""通知是一行一个账号，标签长了就违背精简的初衷。"""
	for status in (STATUS_CHECKED_IN, STATUS_ALREADY_CHECKED, STATUS_AUTO_CHECKED, STATUS_FAILED):
		assert len(CheckInOutcome(status).label) <= 8


def test_auto_label_does_not_claim_confirmed_check_in():
	"""agentrouter 没有签到接口，只能确认"查询成功"，不能声称"签到成功"。"""
	label = CheckInOutcome(STATUS_AUTO_CHECKED).label

	assert '签到成功' not in label
	assert '自动签到' in label


def test_success_semantics():
	assert CheckInOutcome(STATUS_CHECKED_IN).success is True
	assert CheckInOutcome(STATUS_ALREADY_CHECKED).success is True
	assert CheckInOutcome(STATUS_AUTO_CHECKED).success is True
	assert CheckInOutcome(STATUS_FAILED).success is False


def test_unknown_status_is_echoed_not_swallowed():
	assert CheckInOutcome('something_new').label == 'something_new'


# --- format_delta ------------------------------------------------------------------


def test_format_delta():
	assert format_delta(25.0) == '+$25.00'
	assert format_delta(0.0) == '$0.00'
	assert format_delta(-100.0) == '-$100.00'
	assert format_delta(None) == '基线待建立'


def test_format_delta_labels_the_baseline_day():
	"""增量必须说明是跟哪天比的，否则 +$50 会看起来像算错。"""
	assert format_delta(50.0, '2026-09-23') == '+$50.00(较09-23)'
	assert format_delta(0.0, '2026-09-24') == '$0.00(较09-24)'
	assert format_delta(-100.0, '2026-09-23') == '-$100.00(较09-23)'
	assert format_delta(None, '2026-09-24') == '基线待建立'


def test_short_day():
	assert short_day('2026-09-23') == '09-23'
	assert short_day(None) == ''
	assert short_day('') == ''
	assert short_day('weird') == 'weird'


# --- format_account_line -----------------------------------------------------------


def test_line_shows_total_balance_and_gain():
	line = format_account_line(
		'any主帐号',
		CheckInOutcome(STATUS_CHECKED_IN),
		total=2400.0,
		balance=565.45,
		day_gain=25.0,
		baseline_day='2026-09-23',
	)

	assert line == 'any主帐号 · ✅ 签到成功 · 总量 $2400.00 · 余额 $565.45 · +$25.00(较09-23)'


def test_line_explains_a_double_gain_via_baseline_day():
	"""真实案例：+$50 看起来像算错，标出基准日就能自解释。"""
	line = format_account_line(
		'agLD',
		CheckInOutcome(STATUS_AUTO_CHECKED),
		total=1125.0,
		balance=146.55,
		day_gain=50.0,
		baseline_day='2026-09-23',
	)

	assert line.endswith('· +$50.00(较09-23)')


def test_line_shows_balance_even_when_total_unchanged():
	"""余额是你实际在意的数字之一，即使总量没涨也要显示。"""
	line = format_account_line(
		'agLD',
		CheckInOutcome(STATUS_AUTO_CHECKED),
		total=1125.0,
		balance=146.55,
		day_gain=0.0,
	)

	assert '余额 $146.55' in line
	assert line.endswith('· $0.00')


def test_line_omits_balance_when_unknown():
	line = format_account_line('agLD', CheckInOutcome(STATUS_AUTO_CHECKED), total=1075.0, day_gain=25.0)

	assert '余额' not in line
	assert line == 'agLD · ✅ 自动签到 · 总量 $1075.00 · +$25.00'


def test_line_marks_no_growth_explicitly():
	line = format_account_line('agLD', CheckInOutcome(STATUS_AUTO_CHECKED), total=1075.0, day_gain=0.0)

	assert '总量 $1075.00' in line
	assert line.endswith('· $0.00')


def test_line_without_baseline():
	line = format_account_line('agLD', CheckInOutcome(STATUS_AUTO_CHECKED), total=1075.0, day_gain=None)

	assert line == 'agLD · ✅ 自动签到 · 总量 $1075.00 · 基线待建立'


def test_line_reports_negative_gain():
	line = format_account_line('agLD', CheckInOutcome(STATUS_AUTO_CHECKED), total=900.0, day_gain=-100.0)

	assert line.endswith('· -$100.00')


def test_failure_line_shows_reason_instead_of_numbers():
	"""失败时数字没有意义，用原因替代，避免被误读成"没增长"。"""
	line = format_account_line(
		'agLD',
		CheckInOutcome(STATUS_FAILED, '邮箱密码登录失败'),
		total=1075.0,
		day_gain=25.0,
	)

	assert line == 'agLD · ❌ 签到失败 · 邮箱密码登录失败'
	assert '总量' not in line
	assert '+$25.00' not in line


def test_failure_line_without_reason_still_readable():
	line = format_account_line('agLD', CheckInOutcome(STATUS_FAILED))

	assert line == 'agLD · ❌ 签到失败 · 未知原因'


def test_success_line_without_total_omits_amounts():
	"""拿不到用户信息时不能编造数字。"""
	line = format_account_line('agLD', CheckInOutcome(STATUS_AUTO_CHECKED))

	assert line == 'agLD · ✅ 自动签到'


def test_one_line_per_account_has_no_newlines():
	for status in (STATUS_CHECKED_IN, STATUS_ALREADY_CHECKED, STATUS_AUTO_CHECKED, STATUS_FAILED):
		line = format_account_line('acct', CheckInOutcome(status, 'boom'), total=100.0, day_gain=1.0)
		assert '\n' not in line
