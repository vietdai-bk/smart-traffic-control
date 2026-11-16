"""Chống dò mật khẩu nhưng không cho khoá tài khoản người khác, không lộ tài khoản có thật."""
from app.core.login_guard import PER_IP_MAX_FAILS, LoginGuard


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def _fail(g, user, ip, times):
    out = None
    for _ in range(times):
        out = g.record_failure(user, ip)
    return out


def test_lock_is_per_ip_not_per_account():
    g = LoginGuard(Clock())
    _, locked = _fail(g, "admin", "6.6.6.6", 5)
    assert locked > 0 and g.blocked_for("admin", "6.6.6.6") > 0
    assert g.blocked_for("admin", "10.0.0.1") == 0  # admin thật ở IP khác vẫn đăng nhập được


def test_nonexistent_username_behaves_the_same():
    g = LoginGuard(Clock())
    assert _fail(g, "khong-ton-tai", "6.6.6.6", 5)[1] > 0
    assert g.blocked_for("KHONG-TON-TAI", "6.6.6.6") > 0  # không phân biệt hoa thường


def test_lock_expires():
    clock = Clock()
    g = LoginGuard(clock)
    _fail(g, "a", "1.1.1.1", 5)
    clock.t += 6 * 60
    assert g.blocked_for("a", "1.1.1.1") == 0


def test_per_ip_limit_across_usernames():
    g = LoginGuard(Clock())
    for i in range(PER_IP_MAX_FAILS):
        g.record_failure(f"user{i}", "6.6.6.6")  # mỗi tên chỉ sai 1 lần
    assert g.blocked_for("user-moi", "6.6.6.6") > 0
    assert g.blocked_for("user-moi", "7.7.7.7") == 0


def test_success_resets_and_admin_clear():
    g = LoginGuard(Clock())
    _fail(g, "a", "1.1.1.1", 4)
    g.record_success("a", "1.1.1.1")
    assert g.record_failure("a", "1.1.1.1") == (1, 0.0)
    _fail(g, "a", "2.2.2.2", 5)
    g.clear_user("A")
    assert g.blocked_for("a", "2.2.2.2") == 0
