from checkin import (
	STATUS_ALREADY_CHECKED,
	STATUS_AUTO_CHECKED,
	STATUS_CHECKED_IN,
	STATUS_FAILED,
	CheckInOutcome,
	format_check_in_notification,
)


def make_detail(
	name='any主帐号',
	status=STATUS_CHECKED_IN,
	message='',
	reward=0.0,
	usage=0.0,
	before=100.0,
	after=100.0,
):
	return {
		'name': name,
		'before_quota': before,
		'before_used': 900.0,
		'after_quota': after,
		'after_used': 900.0 + usage,
		'check_in_reward': reward,
		'usage_increase': usage,
		'balance_change': after - before,
		'status': status,
		'message': message,
	}


# --- CheckInOutcome.success 语义 -------------------------------------------------


def test_already_checked_and_auto_count_as_success():
	"""今天该账号的签到已完成，因此"重复调用"和"自动触发"都算成功。"""
	assert CheckInOutcome(STATUS_CHECKED_IN).success is True
	assert CheckInOutcome(STATUS_ALREADY_CHECKED).success is True
	assert CheckInOutcome(STATUS_AUTO_CHECKED).success is True
	assert CheckInOutcome(STATUS_FAILED).success is False


def test_labels_distinguish_each_status():
	labels = {
		STATUS_CHECKED_IN: '✅ 签到成功',
		STATUS_ALREADY_CHECKED: '✅ 今日已签到（本次为重复调用）',
		STATUS_AUTO_CHECKED: '✅ 签到成功（查询用户信息时自动触发）',
		STATUS_FAILED: '❌ 签到失败',
	}
	for status, expected in labels.items():
		assert CheckInOutcome(status).label == expected

	# 四种状态的标签必须互不相同，否则通知里又分不出来了
	assert len(set(labels.values())) == 4


def test_unknown_status_is_echoed_not_swallowed():
	assert CheckInOutcome('something_new').label == 'something_new'


# --- format_check_in_notification -------------------------------------------------


def test_each_status_renders_its_own_label():
	"""这是本次修复的核心：不同签到结果不能在通知里渲染成同一句话。"""
	rendered = {
		status: format_check_in_notification(make_detail(status=status))
		for status in (STATUS_CHECKED_IN, STATUS_ALREADY_CHECKED, STATUS_AUTO_CHECKED, STATUS_FAILED)
	}

	assert len(set(rendered.values())) == 4
	for status, text in rendered.items():
		assert CheckInOutcome(status).label in text


def test_misleading_wording_is_gone():
	""" "今日已签到，无变化" 曾让成功/重复/失败看起来一模一样。"""
	for status in (STATUS_CHECKED_IN, STATUS_ALREADY_CHECKED, STATUS_AUTO_CHECKED, STATUS_FAILED):
		text = format_check_in_notification(make_detail(status=status))
		assert '今日已签到，无变化' not in text


def test_reward_is_shown_when_balance_grows():
	text = format_check_in_notification(make_detail(reward=0.5, after=100.5))

	assert '签到获得: +$0.50' in text
	assert '余额变化: +$0.50' in text
	assert '余额无变化' not in text


def test_usage_without_reward_is_reported_as_no_reward():
	text = format_check_in_notification(make_detail(status=STATUS_ALREADY_CHECKED, usage=1.2))

	assert '本次未检测到签到奖励' in text
	assert '期间消耗: $1.20' in text
	assert '签到获得' not in text


def test_unchanged_balance_says_no_change():
	text = format_check_in_notification(make_detail(status=STATUS_AUTO_CHECKED))

	assert '余额无变化' in text
	assert '签到获得' not in text


def test_failure_message_is_included():
	text = format_check_in_notification(make_detail(status=STATUS_FAILED, message='HTTP 401'))

	assert '❌ 签到失败' in text
	assert '说明: HTTP 401' in text


def test_missing_status_field_does_not_crash():
	"""增量/旧配置路径下 detail 可能没有 status，不能因此炸掉通知。"""
	detail = make_detail()
	del detail['status']

	text = format_check_in_notification(detail)

	assert '[CHECK-IN] any主帐号' in text
	assert '余额无变化' in text
