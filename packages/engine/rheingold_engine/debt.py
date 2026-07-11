"""Debt module (spec §8.5): sculpting to a target DSCR, gearing cap, DSRA,
DSCR/LLCR/PLCR.

Sculpting: DS_t = CFADS_t / target for t = 1..T → capacity D0 = Σ DS_t/(1+r)^t.
Gearing cap: D = min(D0, max_gearing × capex); when the cap binds, DS is
rescaled uniformly so PV(DS) = D (DSCR rises above target uniformly).

Principal floor: if rolling the sculpted schedule forward produces negative
principal (back-loaded CFADS), those years become interest-only (P_t = 0) and
the remaining years' payments are re-solved so B_T = 0. Implementation: the
sculpted shape is DS_t(s) = max(s × CFADS_t, I_t) and s is found by bisection
so the terminal balance is zero (s = 1/target on the exact path where the floor
never binds — the golden farm hits the closed-form branch, no iteration error).
Years where the floor binds report DSCR_t = CFADS_t / I_t, which may sit below
target — reported honestly rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

_EPS_BAL = 1e-6  # EUR — terminal-balance tolerance
_MAX_BISECT = 200


@dataclass(frozen=True)
class DebtSchedule:
    debt_capacity: float  # pre-cap PV of sculpted DS (D0)
    debt_drawn: float  # after gearing cap / feasibility
    gearing_cap_binding: bool
    balance_bop: list[float]  # length = life (0 after tenor)
    interest: list[float]
    principal: list[float]
    debt_service: list[float]
    dscr: list[float | None]
    llcr: list[float | None]
    min_dscr: float
    avg_dscr: float
    llcr_1: float
    plcr_1: float
    dsra: float


def _pv(flows: list[float], rate: float) -> float:
    return sum(f / (1.0 + rate) ** (t + 1) for t, f in enumerate(flows))


def _roll(
    debt: float, cfads: list[float], tenor: int, rate: float, s: float
) -> tuple[list[float], list[float], list[float], float]:
    """Roll forward with DS_t = max(s × CFADS_t, I_t) (interest-only floor).

    Returns (interest, principal, debt_service, terminal_balance).
    """
    balance = debt
    interest, principal, service = [], [], []
    for t in range(tenor):
        i_t = rate * balance
        ds_t = max(s * cfads[t], i_t)
        p_t = ds_t - i_t
        # never amortize below zero: clip the final overshoot
        if p_t > balance:
            p_t = balance
            ds_t = i_t + p_t
        interest.append(i_t)
        principal.append(p_t)
        service.append(ds_t)
        balance -= p_t
    return interest, principal, service, balance


def sculpt(
    cfads: list[float],
    life: int,
    tenor: int,
    rate: float,
    target_dscr: float,
    capex: float,
    max_gearing: float,
    dsra_months: int,
) -> DebtSchedule:
    if tenor > life:
        raise ValueError(f"debt tenor ({tenor}y) exceeds project life ({life}y)")
    if tenor <= 0:
        raise ValueError("debt tenor must be positive")
    if any(c <= 0.0 for c in cfads[:tenor]):
        raise ValueError("CFADS must be positive in every tenor year to sculpt debt")

    ds_max = [c / target_dscr for c in cfads[:tenor]]
    d0 = _pv(ds_max, rate)
    cap = max_gearing * capex
    cap_binding = cap < d0
    debt = min(d0, cap)

    # Closed-form branch: uniform s with no floor binding.
    s0 = (debt / d0) / target_dscr  # = 1/target when cap not binding
    interest, principal, service, balance = _roll(debt, cfads, tenor, rate, s0)
    if any(p < -1e-9 for p in principal) or abs(balance) > _EPS_BAL:
        # Floor binds somewhere (or rounding): bisect s so terminal balance = 0.
        lo, hi = 0.0, 1.0 / target_dscr
        # B_T(s) is decreasing in s; ensure hi amortizes fully
        interest, principal, service, bal_hi = _roll(debt, cfads, tenor, rate, hi)
        if bal_hi > _EPS_BAL:
            # even max debt service cannot amortize: reduce the draw by bisection on debt
            d_lo, d_hi = 0.0, debt
            for _ in range(_MAX_BISECT):
                mid = 0.5 * (d_lo + d_hi)
                *_, bal_mid = _roll(mid, cfads, tenor, rate, hi)
                if bal_mid > 0:
                    d_hi = mid
                else:
                    d_lo = mid
                if d_hi - d_lo < _EPS_BAL:
                    break
            debt = d_lo
        for _ in range(_MAX_BISECT):
            s = 0.5 * (lo + hi)
            interest, principal, service, balance = _roll(debt, cfads, tenor, rate, s)
            if balance > 0:
                lo = s
            else:
                hi = s
            if abs(balance) < _EPS_BAL:
                break
        interest, principal, service, balance = _roll(debt, cfads, tenor, rate, hi)
        # absorb the residual into the final principal payment
        if principal:
            principal[-1] += max(0.0, balance)
            service[-1] += max(0.0, balance)
            balance = 0.0

    assert abs(balance) <= max(_EPS_BAL, 1.0), f"debt not amortized: B_T = {balance}"

    dsra = (dsra_months / 12.0) * (sum(service) / len(service)) if service else 0.0

    balance_bop: list[float] = []
    b = debt
    for p in principal:
        balance_bop.append(b)
        b -= p

    dscr: list[float | None] = []
    llcr: list[float | None] = []
    for t in range(life):
        if t < tenor and service[t] > 0:
            dscr.append(cfads[t] / service[t])
        else:
            dscr.append(None)
        if t < tenor and balance_bop[t] > _EPS_BAL:
            pv_rem = _pv(cfads[t:tenor], rate)
            llcr.append((pv_rem + dsra) / balance_bop[t])
        else:
            llcr.append(None)

    dscr_vals = [d for d in dscr if d is not None]
    plcr_1 = ((_pv(cfads[:life], rate) + dsra) / debt) if debt > 0 else float("inf")

    return DebtSchedule(
        debt_capacity=d0,
        debt_drawn=debt,
        gearing_cap_binding=cap_binding,
        balance_bop=balance_bop + [0.0] * (life - tenor),
        interest=interest + [0.0] * (life - tenor),
        principal=principal + [0.0] * (life - tenor),
        debt_service=service + [0.0] * (life - tenor),
        dscr=dscr,
        llcr=llcr,
        min_dscr=min(dscr_vals) if dscr_vals else float("inf"),
        avg_dscr=sum(dscr_vals) / len(dscr_vals) if dscr_vals else float("inf"),
        llcr_1=llcr[0] if llcr and llcr[0] is not None else float("inf"),
        plcr_1=plcr_1,
        dsra=dsra,
    )
