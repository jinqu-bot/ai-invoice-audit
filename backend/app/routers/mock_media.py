"""占位发票图。

D1 没有真实图片，用 SVG 现画一张“像发票”的图，让 B 的详情页今天就有东西看。
D3 起换成 C 用 Pillow 生成的真实版式图，前端把 image_url 换掉即可，其它不用动。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.mock import fixtures

router = APIRouter(prefix="/api/mock", tags=["mock"])

_W, _H = 520, 760


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


@router.get("/invoice-image/{invoice_id}.svg", summary="占位发票图（SVG）")
def invoice_image(invoice_id: str) -> Response:
    detail = fixtures.get_detail(invoice_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"发票不存在：{invoice_id}")

    f = detail["fields"]
    verdict_color = {
        "pass": "#1f9d55",
        "suspect": "#d97706",
        "reject": "#dc2626",
        "manual": "#6366f1",
    }.get(detail["verdict"], "#666")

    rows = []
    y = 430
    for item in f["items"]:
        rows.append(
            f'<text x="40" y="{y}" font-size="15" fill="#333">{_esc(item["name"])}</text>'
            f'<text x="360" y="{y}" font-size="15" fill="#333" text-anchor="end">'
            f'{item["amount"]:.2f}</text>'
        )
        y += 30

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{_H}"
     viewBox="0 0 {_W} {_H}" font-family="Microsoft YaHei, PingFang SC, sans-serif">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <rect x="12" y="12" width="{_W - 24}" height="{_H - 24}" rx="6"
        fill="none" stroke="#c9d4e3" stroke-width="2"/>
  <rect x="12" y="12" width="{_W - 24}" height="{_H - 24}" rx="6"
        fill="none" stroke="{verdict_color}" stroke-width="3" stroke-dasharray="10 6" opacity="0.35"/>

  <text x="{_W / 2}" y="58" font-size="20" font-weight="bold" fill="#1f3b73"
        text-anchor="middle">电子发票（普通发票）</text>
  <text x="{_W / 2}" y="84" font-size="13" fill="#8a94a6"
        text-anchor="middle">浙江省 · 样例数据，非真实票据</text>

  <text x="40" y="120" font-size="13" fill="#666">发票代码</text>
  <text x="120" y="120" font-size="15" fill="#111">{_esc(f["invoice_code"])}</text>
  <text x="300" y="120" font-size="13" fill="#666">发票号码</text>
  <text x="380" y="120" font-size="15" font-weight="bold" fill="#111">{_esc(f["invoice_number"])}</text>
  <text x="40" y="146" font-size="13" fill="#666">开票日期</text>
  <text x="120" y="146" font-size="15" fill="#111">{_esc(f["invoice_date"])}</text>

  <line x1="40" y1="164" x2="{_W - 40}" y2="164" stroke="#e2e8f0"/>

  <text x="40" y="192" font-size="13" fill="#666">购买方名称</text>
  <text x="150" y="192" font-size="14" fill="#111">{_esc(f["buyer_name"])}</text>
  <text x="40" y="218" font-size="13" fill="#666">纳税人识别号</text>
  <text x="150" y="218" font-size="13" fill="#444">{_esc(f["buyer_tax_id"])}</text>

  <line x1="40" y1="238" x2="{_W - 40}" y2="238" stroke="#e2e8f0"/>

  <text x="40" y="266" font-size="13" fill="#666">销售方名称</text>
  <text x="150" y="266" font-size="14" fill="#111">{_esc(f["seller_name"])}</text>
  <text x="40" y="292" font-size="13" fill="#666">纳税人识别号</text>
  <text x="150" y="292" font-size="13" fill="#444">{_esc(f["seller_tax_id"])}</text>

  <rect x="32" y="316" width="{_W - 64}" height="34" fill="#f4f7fb"/>
  <text x="40" y="339" font-size="13" fill="#555">项目名称</text>
  <text x="360" y="339" font-size="13" fill="#555" text-anchor="end">金额</text>

  {''.join(rows)}

  <line x1="40" y1="{y - 4}" x2="{_W - 40}" y2="{y - 4}" stroke="#e2e8f0"/>

  <text x="40" y="{y + 30}" font-size="13" fill="#666">不含税金额</text>
  <text x="360" y="{y + 30}" font-size="14" fill="#111" text-anchor="end">{f["amount_excl_tax"]:.2f}</text>
  <text x="40" y="{y + 56}" font-size="13" fill="#666">税额（税率 {f["tax_rate"] * 100:.0f}%）</text>
  <text x="360" y="{y + 56}" font-size="14" fill="#111" text-anchor="end">{f["tax_amount"]:.2f}</text>

  <rect x="32" y="{y + 74}" width="{_W - 64}" height="44" fill="#eef3fa"/>
  <text x="40" y="{y + 102}" font-size="14" fill="#1f3b73" font-weight="bold">价税合计（小写）</text>
  <text x="360" y="{y + 102}" font-size="19" fill="#1f3b73" font-weight="bold"
        text-anchor="end">¥ {f["amount_incl_tax"]:.2f}</text>

  <text x="{_W / 2}" y="{_H - 40}" font-size="34" fill="#c9d4e3" opacity="0.55"
        text-anchor="middle" font-weight="bold">样 例</text>
</svg>"""

    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})
