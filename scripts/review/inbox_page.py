#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""決策收件匣的頁面（HTML/CSS/JS）。資料與規則在 inbox.py；這裡只管長相與互動。

設計（references/review-page-spec.md §2）：
- 首屏是「簽核牌組」：一次一張決策卡，選一個選項＝簽下這張（蓋章、卡片游走、換下一張）。
- 全部簽完到結尾頁，按「複製全部回覆」才算完成（回覆要貼回對話，Agent 才會照做），成功才放慶祝動畫。
- 漸進增強：沒有 JS 時所有卡照順序列出、點選項一樣複製回覆；JS 才把它變成牌組。
- 視覺沿用鯨工坊（REMIX Studio）：晴海潟湖（亮）／深淵（暗）、鯨魚娘吉祥物。
"""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import stage_views

E = html.escape
MASCOT_DIR = Path(__file__).resolve().parent / "mascot"
TAG_ZH = {"open": "待決", "user": "你裁示", "fail": "重跑", "warn": "附註", "unreviewed": "未驗收"}
WHALE_SVG = ('<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M6 27c0-8 7.5-13 17-13 8 0 13 4 14.5 9.5L42 18c1.4-1.2 '
             '3.4.1 2.8 1.8L42 27.5l2.2 4.6c.7 1.6-1.3 3-2.7 1.9L37 30.5C34.5 36 28.5 38 22 38 12.5 38 6 34 6 27z" fill="#3E7BFF"/>'
             '<path d="M8 30c3 3.6 8 5 14 5s11-1.6 13.6-5.3C31 32 16 32.5 8 30z" fill="#fff" opacity=".92"/>'
             '<circle cx="16" cy="24" r="1.8" fill="#14203F"/><circle cx="13" cy="28" r="1.6" fill="#FF8FA3" opacity=".7"/>'
             '<path d="M19 9c0-2 1.5-3.5 3-3.5M24 11c0-3 2-5 4-5" stroke="#7FE7F2" stroke-width="2" fill="none" stroke-linecap="round"/></svg>')
FAR_WHALE = ('<svg viewBox="0 0 200 80"><path fill="currentColor" d="M4 44C4 22 34 10 74 10c34 0 58 12 70 30l30-20c6-4 14 1 11 8'
             'l-10 22 10 22c3 7-5 12-11 8l-30-20C132 70 104 78 72 78 30 78 4 66 4 44z"/></svg>')


def mascot(state: str, images: bool, alt: str) -> str:
    """鯨魚娘：hero＝吃白飯等你、idle＝沒事睡著、success＝殺青。--no-images 時退回內嵌 SVG 小鯨魚。"""
    path = MASCOT_DIR / f"{state}.webp"
    if images and path.is_file():
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f'<img class="mimg m-{state}" src="data:image/webp;base64,{data}" alt="{E(alt)}">'
    return f'<span class="mimg msvg m-{state}" role="img" aria-label="{E(alt)}">{WHALE_SVG}</span>'


CSS = """
:root{
 --sea0:#F2FBFF;--sea1:#CDEBFA;--sea2:#8FC9EE;--sea3:#4F94D4;--ink:#0A2342;--mute:#4D6A8C;--rule:rgba(10,35,66,.12);
 --glass:rgba(255,255,255,.62);--glass2:rgba(255,255,255,.86);--edge:rgba(255,255,255,.9);
 --shade:0 18px 40px -18px rgba(18,64,128,.38),0 2px 6px rgba(18,64,128,.08);
 --ds:#2B63F0;--glow:#19C3E6;--coral:#E8506A;--okc:#13996A;--bad:#D63A55;--warn:#B57A0C;--ray:rgba(255,255,255,.55);--deep:#0A2A5C;
 --bg:var(--sea1);--panel:rgba(255,255,255,.66);--panel2:rgba(226,242,252,.92);--line:var(--rule);--tx:var(--ink);--mut:var(--mute);--dim:#6C84A3;
 --acc:var(--ds);--accbg:rgba(43,99,240,.10);--hot:var(--coral);--hotbg:rgba(232,80,106,.11);--ok:var(--okc);--okbg:rgba(19,153,106,.11);
 --serif:"Noto Serif TC","Source Han Serif TC",Georgia,serif;
 --sans:"M PLUS Rounded 1c","PingFang TC","Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;
 --ease:cubic-bezier(.22,1,.36,1);--spring:cubic-bezier(.34,1.56,.64,1);color-scheme:light}
@media (prefers-color-scheme:dark){:root{
 --sea0:#06183A;--sea1:#041230;--sea2:#020A1F;--sea3:#010512;--ink:#DCEBFF;--mute:#8AA3CC;--rule:rgba(140,180,255,.16);
 --glass:rgba(8,26,64,.6);--glass2:rgba(14,38,88,.82);--edge:rgba(130,180,255,.2);
 --shade:0 22px 50px -20px rgba(0,0,0,.8),0 0 0 1px rgba(80,140,255,.06);
 --ds:#6E9BFF;--glow:#3CF2DE;--coral:#FF7E93;--okc:#3BD69B;--bad:#FF6479;--warn:#F2B547;--ray:rgba(90,170,255,.13);--deep:#000;
 --panel:rgba(8,26,64,.62);--panel2:rgba(18,44,98,.72);--dim:#6680AE;--accbg:rgba(110,155,255,.14);--hotbg:rgba(255,126,147,.13);--okbg:rgba(59,214,155,.12);
 color-scheme:dark}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;color:var(--tx);font:500 16.5px/1.75 var(--sans);letter-spacing:.02em;-webkit-font-smoothing:antialiased;min-height:100vh;
 background:linear-gradient(180deg,var(--sea0) 0%,var(--sea1) 30%,var(--sea2) 75%,var(--sea3) 100%) fixed}
::selection{background:var(--ds);color:#fff}
.sea{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.rays{position:absolute;inset:-10% -20% 40%;background:linear-gradient(100deg,transparent 0 18%,var(--ray) 20%,transparent 26% 40%,var(--ray) 43%,transparent 47% 60%,var(--ray) 62%,transparent 70%);
 -webkit-mask:linear-gradient(180deg,#000,transparent 90%);mask:linear-gradient(180deg,#000,transparent 90%);filter:blur(14px);transform-origin:50% 0;animation:sway 14s ease-in-out infinite alternate}
@keyframes sway{from{transform:skewX(-8deg) translateX(-3%)}to{transform:skewX(6deg) translateX(3%)}}
.farwhale{position:absolute;top:62%;left:-30vw;width:min(34vw,420px);color:var(--deep);opacity:.07;animation:cruise 80s linear infinite}
@keyframes cruise{to{transform:translateX(160vw)}}
.bub{position:absolute;bottom:-20px;border-radius:50%;border:1.5px solid rgba(255,255,255,.7);background:radial-gradient(circle at 30% 30%,rgba(255,255,255,.8),transparent 60%);animation:rise linear infinite;opacity:0}
@keyframes rise{0%{transform:translate(0,0);opacity:0}10%{opacity:.8}100%{transform:translate(-10px,-110vh);opacity:0}}
.wrap{position:relative;z-index:1;max-width:820px;margin:0 auto;padding:18px 16px 120px}
.glass{background:var(--glass);border:1px solid var(--edge);box-shadow:var(--shade);-webkit-backdrop-filter:blur(16px) saturate(1.3);backdrop-filter:blur(16px) saturate(1.3)}
/* 頁首：鯨魚娘＋對話框＋進度 */
.brand{display:flex;align-items:center;gap:10px;margin:0 0 8px}.brand .logo{width:34px;height:34px;flex:none}.brand .logo svg{width:100%;height:100%}
.brand h1{margin:0;font:800 15px/1.3 var(--sans);letter-spacing:.06em;color:var(--mut)}.brand h1 b{color:var(--tx);font-size:16px}
.hero{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 14px;align-items:end;margin:4px 0 0}
.mascot{margin:0;width:118px;align-self:end}.mimg{display:block;width:100%;height:auto;filter:drop-shadow(0 10px 18px rgba(10,40,100,.25))}
.m-hero{animation:bob 3.6s ease-in-out infinite}@keyframes bob{50%{transform:translateY(-6px)}}
.msvg{width:80px;height:80px}.msvg svg{width:100%;height:100%}
.say{position:relative;border-radius:22px;padding:14px 18px 14px;margin-bottom:18px}
.say::before{content:"";position:absolute;left:-9px;bottom:22px;width:18px;height:18px;background:inherit;border-left:1px solid var(--edge);border-bottom:1px solid var(--edge);transform:rotate(45deg);border-radius:0 0 0 5px}
.say .who{display:inline-block;font:800 11.5px/1 var(--sans);letter-spacing:.14em;color:var(--glow);text-transform:uppercase;margin-bottom:6px}
.big{font:900 26px/1.35 var(--serif);margin:0;letter-spacing:.03em}.big em{font-style:normal;color:var(--hot);font-size:1.25em;padding:0 2px}
.sub{color:var(--mut);margin:4px 0 0;font-size:14.5px}.progress{font-variant-numeric:tabular-nums}
.stages{list-style:none;padding:12px 10px 10px;margin:4px 0 0;display:grid;grid-template-columns:repeat(8,1fr);gap:2px;border-radius:18px}
.st{display:flex;flex-direction:column;align-items:center;position:relative}
.st::before{content:"";position:absolute;top:15px;left:-50%;width:100%;height:3px;border-radius:2px;background:var(--rule);z-index:0}
.st:first-child::before{display:none}.st.done::before,.st.cur::before{background:linear-gradient(90deg,var(--glow),var(--ds))}
.stl{display:flex;flex-direction:column;align-items:center;gap:5px;text-decoration:none;color:inherit}.stl:focus-visible .dot{outline:2px solid var(--ds);outline-offset:2px}
.dot{position:relative;z-index:1;width:32px;height:32px;border-radius:50%;display:grid;place-items:center;font:800 14px/1 var(--sans);background:var(--glass2);color:var(--dim);border:2px solid var(--rule)}
.done .dot{background:var(--okbg);color:var(--ok);border-color:var(--ok)}
.cur .dot{background:var(--ds);color:#fff;border-color:var(--ds);box-shadow:0 0 0 6px var(--accbg),0 0 18px var(--glow)}
.nm{font-size:12px;color:var(--mut);white-space:nowrap;letter-spacing:0}.cur .nm{color:var(--tx);font-weight:800}
.block{margin:12px 0 0;border-radius:14px;padding:10px 14px;font-size:14.5px;background:var(--hotbg);border:1px solid color-mix(in srgb,var(--hot) 40%,transparent);word-break:break-word}
.block b{color:var(--hot)}.block.calm{background:var(--okbg);border-color:color-mix(in srgb,var(--ok) 40%,transparent)}.block.calm b{color:var(--ok)}
.notes{margin:10px 0 0;padding:0;list-style:none;font-size:14px;color:var(--mut)}
h2{font:900 21px/1.4 var(--serif);margin:34px 0 12px;letter-spacing:.04em}h2 .n{display:block;font:500 13.5px/1.5 var(--sans);color:var(--mut);margin-top:2px;letter-spacing:.02em}
/* 簽核牌組 */
.deckzone{margin-top:22px}
.dhead{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap}.dhead h2{margin:0}
.counter{font:800 14px/1 var(--sans);color:var(--mut);font-variant-numeric:tabular-nums}
.dots,.dnav,.signbar,.finale,.seal{display:none}
.deck-on .dots{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0 14px}
.pip{all:unset;cursor:pointer;width:30px;height:9px;border-radius:99px;background:var(--rule);transition:background .3s,width .3s var(--ease)}
.pip.b0,.pip.b1{background:color-mix(in srgb,var(--hot) 35%,transparent)}.pip.b2{background:color-mix(in srgb,var(--warn) 35%,transparent)}
.pip.on{width:46px;background:var(--ds)}.pip.ok{background:var(--ok)}.pip:focus-visible{outline:2px solid var(--ds);outline-offset:3px}
.deck{position:relative}.deck-on .deck{overflow-x:clip}body{overflow-x:clip}
figure img.mimg{background:none;border-radius:0}
.card{position:relative;border-radius:24px;padding:20px 18px 16px;margin:0 0 16px;overflow:hidden}
.card::after{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--rule)}
.card.b0::after,.card.b1::after{background:var(--hot)}.card.b2::after{background:var(--warn)}
.deck-on .deck .stk{position:absolute;inset:0 0 auto 0;margin:0;transition:transform .6s var(--ease),opacity .45s ease;will-change:transform}
.deck-on .deck .stk.is-active{position:relative;z-index:5}
.deck-on .deck .stk:not(.is-active){pointer-events:none;height:100%;opacity:0}
.deck-on .deck .stk:not(.is-active)>*{visibility:hidden}
.deck-on .deck .stk.is-n1{opacity:.75;z-index:4;transform:translateY(14px) scale(.955)}
.deck-on .deck .stk.is-n2{opacity:.45;z-index:3;transform:translateY(28px) scale(.91)}
.deck-on .deck .stk.is-gone{transform:translateX(-118%) rotate(-9deg);opacity:0}
.deck-on .deck .stk.is-back{transform:translateX(118%) rotate(9deg);opacity:0}
.deck-on .deck{margin-bottom:34px}
.meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:13px}
.tag{padding:2px 11px;border-radius:99px;background:var(--panel2);color:var(--mut);border:1px solid var(--rule);font-weight:800}
.tag.b0,.tag.b1{background:var(--hotbg);color:var(--hot);border-color:color-mix(in srgb,var(--hot) 45%,transparent)}
.tag.b2{background:color-mix(in srgb,var(--warn) 14%,transparent);color:var(--warn);border-color:color-mix(in srgb,var(--warn) 45%,transparent)}
.seg{color:var(--dim);word-break:break-all}.cno{margin-left:auto;color:var(--dim);font-variant-numeric:tabular-nums;font-weight:800}
.card h3{font:900 22px/1.5 var(--serif);margin:10px 0 10px;word-break:break-word;letter-spacing:.02em}.card h3:focus{outline:none}
figure{margin:4px 0 12px}figure img{display:block;width:100%;height:auto;border-radius:12px;background:#000}
figure img+img{margin-top:6px}figcaption{font-size:13px;color:var(--dim);margin-top:6px}
dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:6px 14px}dt{font-size:13.5px;color:var(--dim);padding-top:2px;white-space:nowrap;font-weight:800}
dd{margin:0;color:var(--tx);word-break:break-word;opacity:.92}dd.recd{opacity:1;font-weight:800;color:var(--ds)}
.opts{display:grid;gap:9px;margin-top:16px}
.opt{all:unset;cursor:pointer;position:relative;display:flex;flex-direction:column;gap:2px;padding:13px 16px 13px 52px;border-radius:16px;background:var(--glass2);border:1.5px solid var(--rule);
 transition:transform .2s var(--spring),border-color .2s,background .2s,box-shadow .2s;-webkit-tap-highlight-color:transparent}
.opt:hover{transform:translateY(-2px);border-color:color-mix(in srgb,var(--ds) 50%,transparent);box-shadow:0 10px 22px -14px rgba(20,70,160,.5)}
.opt:active{transform:scale(.98)}.opt:focus-visible{outline:3px solid var(--glow);outline-offset:2px}
.opt kbd{position:absolute;left:14px;top:13px;width:26px;height:26px;border-radius:9px;display:grid;place-items:center;font:800 13px/1 var(--sans);background:var(--panel2);color:var(--mut);border:1px solid var(--rule)}
.opt.rec{border-color:color-mix(in srgb,var(--ds) 55%,transparent);background:linear-gradient(135deg,var(--accbg),var(--glass2))}.opt.rec kbd{background:var(--ds);color:#fff;border-color:var(--ds)}
.ol{font-weight:800;font-size:16.5px}.opt.rec .ol::after{content:"建議";display:inline-block;white-space:nowrap;margin-left:8px;font-size:11.5px;font-weight:800;color:var(--ds);border:1px solid color-mix(in srgb,var(--ds) 55%,transparent);border-radius:99px;padding:0 8px;vertical-align:2px}
.ot{font-size:13.5px;color:var(--mut);line-height:1.55;word-break:break-word}
.opt.off{cursor:not-allowed;opacity:.45;filter:grayscale(1)}.opt.off:hover{transform:none;box-shadow:none;border-color:var(--rule)}
.opt.picked{border-color:var(--ok);background:var(--okbg)}.opt.picked kbd{background:var(--ok);color:#fff;border-color:var(--ok)}
.opt.picked .ol::before{content:"✓ ";color:var(--ok)}
.deck-on .seal{display:grid;position:absolute;right:20px;top:44px;width:84px;height:84px;place-items:center;border-radius:50%;border:3px double var(--coral);color:var(--coral);
 font:900 22px/1 var(--serif);letter-spacing:.1em;transform:rotate(-16deg) scale(2.4);opacity:0;pointer-events:none;transition:transform .45s var(--spring),opacity .2s;z-index:6;
 background:radial-gradient(circle,color-mix(in srgb,var(--coral) 10%,transparent),transparent 70%)}
.deck-on .signed>.seal{opacity:.9;transform:rotate(-16deg) scale(1)}
.links{margin-top:12px;display:flex;flex-wrap:wrap;gap:14px}.lnk{color:var(--acc);text-decoration:none;font-size:15px;font-weight:700}.lnk:hover{text-decoration:underline}
.src{color:var(--dim);font-size:12.5px;margin:12px 0 0;word-break:break-word}
.deck-on .dnav{display:flex;justify-content:space-between;align-items:center;gap:10px;margin:-18px 0 0}
.nb{all:unset;cursor:pointer;padding:9px 16px;border-radius:99px;font-weight:800;font-size:14.5px;color:var(--mut);background:var(--glass);border:1px solid var(--edge)}
.nb:hover{color:var(--tx)}.nb:focus-visible{outline:2px solid var(--ds)}.nb[disabled]{opacity:.35;pointer-events:none}
/* 結尾：簽完 → 複製全部回覆才算完成 */
.deck-on .finale{display:block;text-align:center;border-radius:28px;padding:22px 18px 22px}
.finale .mascot{width:170px;margin:0 auto}.finale h3{font:900 25px/1.4 var(--serif);margin:6px 0 4px}
.finale .must{display:inline-block;margin:6px 0 12px;padding:3px 12px;border-radius:99px;background:var(--hotbg);color:var(--hot);font-weight:800;font-size:14px}
.finale ol{text-align:left;margin:0 auto 16px;max-width:560px;padding-left:1.4em;font-size:14.5px;color:var(--mut)}.finale ol b{color:var(--tx)}
.finale .left{color:var(--warn);font-weight:800;margin:0 0 10px}
.cta{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:10px;padding:15px 28px;border-radius:99px;font:800 17px/1 var(--sans);color:#fff;letter-spacing:.06em;
 background:linear-gradient(135deg,var(--glow),var(--ds));box-shadow:0 14px 30px -12px var(--ds),inset 0 1px 0 rgba(255,255,255,.4);transition:transform .2s var(--spring)}
.cta:hover{transform:translateY(-2px) scale(1.02)}.cta:active{transform:scale(.97)}.cta:focus-visible{outline:3px solid var(--glow);outline-offset:3px}
.finale.cheer .mimg{animation:jump .9s var(--spring) 2}@keyframes jump{30%{transform:translateY(-26px) rotate(-4deg)}60%{transform:translateY(0) rotate(3deg)}}
.finale textarea{display:block;width:100%;max-width:560px;margin:14px auto 0;min-height:5.5em;border-radius:12px;border:1px solid var(--rule);background:var(--glass2);color:var(--tx);font:500 13.5px/1.6 var(--sans);padding:10px 12px;resize:vertical}
.finale .done-msg{display:none;margin:12px 0 0;font-weight:800;color:var(--ok)}.finale.cheer .done-msg{display:block}
.pt{position:fixed;z-index:50;pointer-events:none;left:0;top:0;animation:pop 1.1s var(--ease) forwards}
.pt.b{width:var(--s);height:var(--s);border-radius:50%;border:2px solid var(--glow);background:radial-gradient(circle at 30% 30%,rgba(255,255,255,.9),transparent 60%)}
.pt.k{font-size:var(--s);color:var(--c);line-height:1}
@keyframes pop{0%{transform:translate(var(--x0),var(--y0)) scale(.3);opacity:1}100%{transform:translate(calc(var(--x0) + var(--dx)),calc(var(--y0) + var(--dy))) scale(1) rotate(var(--r));opacity:0}}
.deck-on .signbar{display:flex;position:fixed;z-index:20;left:50%;bottom:14px;transform:translateX(-50%) translateY(140%);transition:transform .5s var(--spring);align-items:center;gap:12px;
 padding:8px 8px 8px 18px;border-radius:99px;max-width:calc(100vw - 24px);white-space:nowrap}
.deck-on .signbar.on{transform:translateX(-50%) translateY(0)}.signbar b{font-variant-numeric:tabular-nums}
.signbar .cta{padding:10px 18px;font-size:14.5px}
.hint{text-align:center;margin:8px 0 0}.hint a{color:var(--mut);text-decoration:none;font-weight:800;font-size:14px}
/* 其餘區塊（收合） */
.fold{background:var(--glass);border:1px solid var(--edge);box-shadow:var(--shade);border-radius:20px;margin:0 0 14px;overflow:hidden;-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)}
.fold>summary{list-style:none;cursor:pointer;padding:14px 18px;font-size:17px;font-weight:800;display:flex;justify-content:space-between;align-items:center;gap:10px}
.fold>summary::-webkit-details-marker,.kd>summary::-webkit-details-marker,.ep>summary::-webkit-details-marker{display:none}
.fold>summary::after{content:"展開";font-size:13px;font-weight:800;color:var(--ds);flex:0 0 auto;padding:2px 10px;border-radius:99px;background:var(--accbg)}.fold[open]>summary::after{content:"收合"}
.ft{display:flex;flex-direction:column;gap:2px}.fold>summary small{font-size:13.5px;color:var(--mut);font-weight:500;line-height:1.5}
.fold .card{box-shadow:none;margin:0 12px 12px;background:var(--glass2)}
.kd{border-top:1px solid var(--rule)}.kd>summary{list-style:none;cursor:pointer;display:flex;gap:12px;padding:11px 18px;align-items:flex-start}
.kt{flex:0 0 auto;font-size:13px;color:var(--dim);font-variant-numeric:tabular-nums;padding-top:2px;min-width:86px}
.ck{flex:0 0 auto;color:var(--ok);font-weight:800}.kx{display:flex;flex-direction:column;min-width:0}.kx b{font-size:15.5px}
.kv{color:var(--mut);font-size:14.5px;line-height:1.6;word-break:break-word}.kv.strong{color:var(--tx);font-size:15.5px}
.kd p{margin:0 18px 10px 116px;font-size:14px;color:var(--mut);line-height:1.7;word-break:break-word}
.kd p.src{color:var(--dim);font-size:12.5px}#auto .kd p,.card .kd p{margin-left:18px}
.kd.signed>summary .kx b::before{content:"✓ ";color:var(--ok)}
.empty{color:var(--mut);padding:14px 18px;margin:0}
.calmcard{text-align:center}.calmcard .mascot{width:150px;margin:0 auto}.calmcard dl{display:block}.calmcard dd{margin-top:4px}
.duo{display:grid;gap:0 16px}
.vrow{display:flex;gap:10px;overflow-x:auto;padding:2px 0 10px;scroll-snap-type:x mandatory}.vrow .vid{flex:0 0 78%;max-width:340px;scroll-snap-align:start}
.vid{all:unset;cursor:pointer;display:flex;flex-direction:column;gap:6px;background:var(--glass);border:1px solid var(--edge);border-radius:14px;padding:8px}
.vid:focus-visible{outline:2px solid var(--ds)}.vimg img,.vimg video{display:block;width:100%;height:auto;border-radius:8px;background:#000}
.noimg{display:grid;place-items:center;aspect-ratio:16/6;border-radius:8px;background:var(--panel2);color:var(--dim);font-size:13px}
.vn{font-size:14px;color:var(--mut);display:flex;gap:8px;align-items:center;font-variant-numeric:tabular-nums}
.vt{font-size:11.5px;padding:0 7px;border-radius:99px;border:1px solid var(--rule)}
.v-open,.v-fail{color:var(--hot);border-color:color-mix(in srgb,var(--hot) 50%,transparent)}.v-user,.v-warn{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 45%,transparent)}.v-unreviewed{color:var(--dim)}
.ep{border-top:1px solid var(--rule)}.ep>summary{list-style:none;cursor:pointer;padding:12px 18px;font-weight:800;display:flex;justify-content:space-between}
.cnt{color:var(--dim);font-weight:500;font-size:14px}.vgrid{display:grid;grid-template-columns:1fr;gap:10px;padding:0 12px 14px}
.raw{font-size:13.5px;color:var(--mut);margin-top:30px;border-top:1px solid var(--rule);padding-top:14px}.raw a{color:var(--mut)}.raw ul{margin:6px 0 0;padding-left:18px}
.toast{position:fixed;z-index:60;left:50%;top:18px;transform:translateX(-50%) translateY(-20px);opacity:0;background:var(--ink);color:var(--sea0);font-weight:800;padding:10px 18px;border-radius:99px;transition:.25s var(--ease);pointer-events:none;font-size:14.5px;max-width:90vw;text-align:center}
.toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
@media (min-width:900px){.wrap{padding:34px 32px 130px}.big{font-size:32px}.mascot{width:150px}.card{padding:26px 28px 20px}.card h3{font-size:25px}
 .nm{font-size:13.5px}.duo{grid-template-columns:1fr 1fr}.vrow .vid{flex-basis:46%}.vgrid{grid-template-columns:1fr 1fr}}
@media (max-width:560px){.mascot{width:92px}.big{font-size:22px}.say{padding:12px 14px}.card{padding:18px 15px 14px}.card h3{font-size:20px}
 .deck-on .seal{width:66px;height:66px;font-size:18px;right:12px}.kd p{margin-left:18px}.signbar{font-size:14px}}
@media (max-width:380px){.nm{font-size:10.5px}.dot{width:27px;height:27px}.st::before{top:12px}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}.bub,.farwhale,.pt{display:none}}
"""

JS = r"""
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const toast=$('#toast');let tt;
function say(m){toast.textContent=m;toast.classList.add('on');clearTimeout(tt);tt=setTimeout(()=>toast.classList.remove('on'),2000)}
async function copy(t){try{await navigator.clipboard.writeText(t);return true}catch(e){
 const a=document.createElement('textarea');a.value=t;a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.select();
 let ok=false;try{ok=document.execCommand('copy')}catch(_){};a.remove();return ok}}
const calm=matchMedia('(prefers-reduced-motion: reduce)').matches;
(function sea(){const box=$('#bubbles');if(!box||calm)return;for(let i=0;i<14;i++){const b=document.createElement('i');b.className='bub';const s=6+Math.random()*16;
 b.style.cssText=`left:${Math.random()*100}%;width:${s}px;height:${s}px;animation-duration:${10+Math.random()*14}s;animation-delay:${-Math.random()*20}s`;box.appendChild(b)}})();
function burst(x,y,n,big){if(calm)return;const glyph=['✦','✧','♡','✦'];const col=['var(--glow)','var(--ds)','var(--coral)','#F2B547'];
 for(let i=0;i<n;i++){const p=document.createElement('i');const kind=Math.random()<.55?'b':'k';p.className='pt '+kind;if(kind==='k')p.textContent=glyph[i%4];
  const a=Math.random()*Math.PI*2,d=(big?140:60)+Math.random()*(big?260:90);
  p.style.cssText=`--x0:${x}px;--y0:${y}px;--dx:${Math.cos(a)*d}px;--dy:${Math.sin(a)*d-(big?120:40)}px;--r:${(Math.random()-.5)*240}deg;--s:${kind==='b'?8+Math.random()*16:12+Math.random()*14}px;--c:${col[i%4]}`;
  document.body.appendChild(p);setTimeout(()=>p.remove(),1200)}}
const KEY='h3d-inbox:'+document.body.dataset.key;let ans={};
try{ans=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(_){ans={}}
function save(){try{localStorage.setItem(KEY,JSON.stringify(ans))}catch(_){}}
const units=()=>$$('[data-sign]').filter(u=>ans[u.id]);
function allReplies(){return units().map(u=>ans[u.id].reply).join('\n')}
function mark(u){const a=ans[u.id];u.classList.toggle('signed',!!a);
 $$(':scope > .opts .opt, :scope > div > .opts .opt',u).forEach(o=>o.classList.toggle('picked',!!a&&o.dataset.reply===a.reply))}
const deck=$('.deck'),stack=deck?$$('.stk',deck):[],cards=stack.filter(s=>s.classList.contains('card')),fin=$('#finale');
const bar=$('.signbar'),live=$('#live');let cur=0;
function refresh(){$$('[data-sign]').forEach(mark);const k=units().length,hard=cards.filter(c=>ans[c.id]).length;
 if(bar){bar.classList.toggle('on',k>0);$('#k',bar).textContent=k;$('#kh',bar).textContent=hard+'／'+cards.length}
 $$('.pip').forEach((p,i)=>p.classList.toggle('ok',!!(cards[i]&&ans[cards[i].id])));
 if(fin){const left=cards.filter(c=>!ans[c.id]).length;$('#fin-n',fin).textContent=hard;
  $('#fin-left',fin).hidden=!left;$('#fin-left b',fin).textContent=left;
  $('#fin-list',fin).innerHTML=units().map(u=>`<li><b>${esc(ans[u.id].label)}</b>　${esc(ans[u.id].title)}</li>`).join('');
  $('#fin-text',fin).value=allReplies()}}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function go(i){if(!stack.length)return;const back=i<cur;cur=Math.max(0,Math.min(i,stack.length-1));
 stack.forEach((s,j)=>{s.classList.remove('is-active','is-n1','is-n2','is-gone','is-back');
  if(j===cur)s.classList.add('is-active');else if(j===cur+1)s.classList.add('is-n1');else if(j===cur+2)s.classList.add('is-n2');
  else s.classList.add(j<cur?'is-gone':'is-back');s.setAttribute('aria-hidden',j===cur?'false':'true');s.inert=j!==cur});
 const onFin=cur>=cards.length;$('#counter').textContent=onFin?'全部看完':`第 ${cur+1}／${cards.length} 張${TOTAL>cards.length?`・共 ${TOTAL} 件`:''}`;
 $$('.pip').forEach((p,j)=>{p.classList.toggle('on',j===cur);p.setAttribute('aria-current',j===cur?'step':'false')});
 $('#prev').disabled=cur===0;$('#next').disabled=onFin;
 const h=$('h3',stack[cur]);if(h&&document.activeElement&&document.activeElement.closest('.deckzone')){h.setAttribute('tabindex','-1');h.focus({preventScroll:true})}
 if(live)live.textContent=onFin?'全部看完，最後一步：複製全部回覆':`第 ${cur+1} 張：${h?h.textContent:''}`;void back}
const TOTAL=+(document.body.dataset.total||0);
document.addEventListener('click',async e=>{const o=e.target.closest('button.opt');if(!o)return;
 const u=o.closest('[data-sign]');if(!u)return;const title=u.dataset.title||'';
 ans[u.id]={reply:o.dataset.reply,label:$('.ol',o).textContent,title};save();refresh();
 const r=o.getBoundingClientRect();burst(r.left+30,r.top+r.height/2,14,false);
 const ok=await copy(o.dataset.reply);
 if(document.body.classList.contains('deck-on')&&u===stack[cur]){say('已簽：'+ans[u.id].label);setTimeout(()=>go(cur+1),620)}
 else say(ok?'已簽並複製：'+ans[u.id].label:'已簽（複製失敗，可最後一起複製）')});
async function copyAll(btn){const t=allReplies();if(!t){say('還沒有簽任何一張');return}
 const ok=await copy(t);if(!ok){const box=fin&&$('#fin-text',fin);if(box&&fin.classList.contains('is-active')){box.focus();box.select()}
  say('複製失敗：回覆已選取在下方文字框，按 Ctrl+C 或長按複製');return}
 say(`已複製 ${units().length} 則回覆，貼回對話就完成`);
 if(fin&&btn&&fin.contains(btn)){fin.classList.add('cheer');const r=$('.mascot',fin).getBoundingClientRect();burst(r.left+r.width/2,r.top+r.height/2,46,true)}}
$$('[data-copyall]').forEach(b=>b.addEventListener('click',()=>copyAll(b)));
if(stack.length){document.body.classList.add('deck-on');
 $$('.pip').forEach((p,i)=>p.addEventListener('click',()=>go(i)));
 $('#prev').addEventListener('click',()=>go(cur-1));$('#next').addEventListener('click',()=>go(cur+1));
 const back=$('#fin-left button');if(back)back.addEventListener('click',()=>go(cards.findIndex(c=>!ans[c.id])));
 document.addEventListener('keydown',e=>{if(e.target.closest('input,textarea')||e.metaKey||e.ctrlKey||e.altKey)return;
  if(e.key==='ArrowRight')go(cur+1);else if(e.key==='ArrowLeft')go(cur-1);
  else if(/^[1-3]$/.test(e.key)&&stack[cur]&&cards.includes(stack[cur])){const o=$$(':scope > .opts button.opt',stack[cur])[+e.key-1];if(o)o.click()}});
 const first=cards.findIndex(c=>!ans[c.id]);refresh();go(first<0?cards.length:first)}else refresh();
if(matchMedia('(min-width:900px)').matches)$$('.duo details.fold').forEach(d=>d.open=true);
$$('.vid').forEach(b=>b.addEventListener('click',()=>{const box=$('.vimg',b);if($('video',box))return;
 const v=document.createElement('video');v.src=b.dataset.src;v.controls=true;v.autoplay=true;v.playsInline=true;v.preload='metadata';box.innerHTML='';box.appendChild(v)}));
"""


def _opts(options: List[Dict[str, Any]], limit: int = 3, *, rec: bool = True,
          unavailable: Optional[List[Dict[str, Any]]] = None) -> str:
    """選項按鈕；rec=False 時不標「建議」。unavailable：灰掉、不能點的選項（附原因），例如偵測不到的生圖工具。"""
    buttons = "".join(
        f'<button class="opt{" rec" if i == 0 and rec else ""}" data-reply="{E(o["reply"])}"><kbd>{i + 1}</kbd>'
        f'<span class="ol">{E(o["label"])}</span><span class="ot">{E(o["reply"])}</span></button>'
        for i, o in enumerate(options[:limit]))
    off = "".join(
        f'<div class="opt off" aria-disabled="true"><kbd>—</kbd><span class="ol">{E(o["label"])}（不可用）</span>'
        f'<span class="ot">{E(o.get("reason", ""))}</span></div>'
        for o in (unavailable or []))
    return buttons + off


def card_html(c: Dict[str, Any], *, n: int = 0, of: int = 0, deck: bool = False) -> str:
    links = "".join(f'<a class="lnk" href="{E(l["href"])}" target="_blank" rel="noopener">{E(l["label"])} ↗</a>'
                    for l in c.get("links", []))
    fig = ""
    if c.get("evidence_b64"):
        imgs = "".join(f'<img src="{src}" alt="{E(c.get("evidence_caption", "證據"))}">' for src in c["evidence_b64"])
        fig = f'<figure>{imgs}<figcaption>{E(c.get("evidence_caption", ""))}</figcaption></figure>'
    cno = f'<span class="cno">{n}／{of}</span>' if of else ""
    finding = f'<dt>判定</dt><dd>{E(c["finding"])}</dd>' if c.get("finding") else ""
    return f'''
<article class="card glass b{c["blocking"]}{" stk" if deck else ""}" id="{E(c["id"])}" data-sign data-title="{E(c["title"])}">
  <div class="seal" aria-hidden="true">已簽</div>
  <div class="meta"><span class="tag b{c["blocking"]}">{E(c["blocking_label"])}</span><span class="seg">階段 {c["stage"]}・{E(str(c["segment"]))}</span>{cno}</div>
  <h3>{E(c["title"])}</h3>
  {fig}
  <dl>{finding}<dt>影響</dt><dd>{E(c["impact"])}</dd><dt>建議</dt><dd class="recd">{E(c["recommendation"])}</dd><dt>不回覆</dt><dd>{E(c.get("if_ignored", ""))}</dd></dl>
  <div class="opts">{_opts(c["options"], 9, rec=not c.get("no_recommendation"), unavailable=c.get("unavailable_options"))}</div>
  {f'<div class="links">{links}</div>' if links else ""}
  {children_html(c.get("children") or [])}
  <p class="src">卡片 {E(c["id"])}・來源 {E(c.get("source", ""))}</p>
</article>'''


def children_html(children: List[Dict[str, Any]]) -> str:
    """合併卡裡的每一件：可逐件讀、逐件簽（簽在子卡上，不換張）。"""
    if not children:
        return ""
    rows = "".join(
        f'<details class="kd" id="{E(ch["id"])}" data-sign data-title="{E(ch["title"])}"><summary><span class="kx"><b>{E(ch["title"])}</b>'
        f'<span class="kv">階段 {ch["stage"]}・{E(str(ch.get("segment", "")))}・{E(ch.get("blocking_label", ""))}</span></span></summary>'
        f'<p>{E(ch.get("finding") or "")} 影響：{E(ch["impact"])} 建議：{E(ch["recommendation"])}</p>'
        f'<div style="margin:0 16px 12px"><div class="opts">{_opts(ch["options"])}</div></div>'
        f'<p class="src">卡片 {E(ch["id"])}・來源 {E(str(ch.get("source", "")))}</p></details>'
        for ch in children)
    return (f'<details class="fold" style="margin-top:14px;box-shadow:none"><summary><span class="ft">逐件展開 {len(children)} 件'
            f'<small>上面的選項一次簽整批；也可以在這裡逐件簽</small></span></summary>{rows}</details>')


def _decided_html(d: Dict[str, Any]) -> str:
    return (f'<details class="kd"><summary><span class="kt">{E(d["time"])}</span><span class="kx"><b>{E(d["title"])}</b>'
            f'<span class="kv">{E(d["decision"])}</span></span></summary><p>{E(d["detail"])}</p>'
            f'<p class="src">階段 {d["stage"]}・出處 {E(d["source"])}</p></details>')


def _auto_html(a: Dict[str, Any]) -> str:
    return (f'<details class="kd"><summary><span class="ck">✓</span><span class="kx"><span class="kv strong">{E(a["text"])}</span>'
            f'</span></summary><p>{E(a["detail"])}</p><p class="src">來源：{E(a["source"])}</p></details>')


def _vid_html(v: Dict[str, Any]) -> str:
    tag = TAG_ZH.get(v["tag"], "")
    t = f'<span class="vt v-{E(v["tag"])}">{tag}</span>' if tag else ""
    img = (f'<img src="{v["strip"]}" alt="{E(v["segment"])} 10 幀條">' if v.get("strip")
           else '<div class="noimg">點一下載入影片</div>')
    return (f'<button class="vid" data-src="{E(v["video"])}"><span class="vimg">{img}</span>'
            f'<span class="vn">{E(v["segment"])}{t}</span></button>')


def _deck_html(hard: List[Dict[str, Any]], total: int, images: bool) -> str:
    if not hard:
        sleep = mascot("idle", images, "鯨魚娘睡著了")
        return (f'<article class="card glass calmcard"><figure class="mascot">{sleep}</figure>'
                '<h3>沒有擋關的待決事項</h3><dl><dt>下一步</dt>'
                '<dd class="recd">照 h3d next 繼續；符合授權的階段可用 h3d approve --auto 自動核准。</dd></dl></article>')
    n = len(hard)
    pips = "".join(f'<button class="pip b{c["blocking"]}" aria-label="第 {i + 1} 張：{E(c["title"])}"></button>'
                   for i, c in enumerate(hard))
    cards = "".join(card_html(c, n=i + 1, of=n, deck=True) for i, c in enumerate(hard))
    finale = f'''
<section class="finale glass stk" id="finale" aria-label="簽核完成">
  <figure class="mascot">{mascot("success", images, "鯨魚娘殺青")}</figure>
  <h3>簽好 <span id="fin-n">0</span> 張了！</h3>
  <p class="must">最後一步：複製回覆、貼回對話才算數</p>
  <p class="left" id="fin-left" hidden>還有 <b>0</b> 張沒簽　<button class="nb" type="button">回去簽</button></p>
  <ol id="fin-list"></ol>
  <button class="cta" type="button" data-copyall>複製全部回覆</button>
  <textarea id="fin-text" readonly aria-label="全部回覆（複製失敗時可手動全選複製）"></textarea>
  <p class="done-msg">已複製！貼回對話，鯨魚娘就去開工 🐋</p>
</section>'''
    return f'''
<div class="dots" role="tablist" aria-label="決策卡">{pips}</div>
<div class="deck">{cards}{finale}</div>
<div class="dnav"><button class="nb" id="prev" type="button">← 上一張</button><button class="nb" id="next" type="button">稍後再看 →</button></div>'''


def render(model: Dict[str, Any], short_title: Callable[[str, int], str], stage_short: List[str]) -> str:
    cards = model["cards"]
    cur = model["current_stage"]
    images = bool(model.get("images", True))
    bar = "".join(
        f'<li class="st {"done" if s["status"] == "approved" else ("cur" if s["current"] else "todo")}">'
        f'<a class="stl" href="#stage-{s["n"]}"><span class="dot">{s["n"]}</span><span class="nm">{E(s["name"])}</span></a></li>'
        for s in model["stages"])
    total = model.get("pending_total", len(cards))
    hard = [x for x in cards if x["blocking"] <= 2]
    soft = [x for x in cards if x["blocking"] > 2]
    big = f'有 <em>{total}</em> 件事等你決定' if cards else '目前沒有要你決定的事'
    who = "鯨魚娘吃白飯中・等你簽核" if hard else ("鯨魚娘在摸魚・只剩不擋關的小事" if cards else "鯨魚娘睡著了・沒有要簽的")
    c = model.get("counts") or {}
    stuck = short_title(hard[0]["title"], 24) if hard else "沒有"
    progress = f'階段{cur}/7・{total}件待決・卡在{E(stuck)}'
    sub = f'目前在階段 {cur}「{E(stage_short[cur])}」'
    if c:
        sub += f'・影片 通過 {c.get("pass", 0)}・附註 {c.get("warn", 0)}・重跑 {c.get("fail", 0)}'
    if model["blocker"]:
        calm = "" if hard else " calm"
        block = f'<p class="block{calm}"><b>{"狀態：" if calm else "卡在這裡："}</b>{E(model["blocker"])}</p>'
    else:
        block = '<p class="block calm"><b>狀態：</b>沒有擋住的事，可以往下走</p>'
    notes = "".join(f"<li>・{E(n)}</li>" for n in model.get("notes", []))
    videos = model.get("videos", [])
    vmap = {v["segment"]: v for v in videos}
    recent = "".join(_vid_html(vmap[s]) for s in model.get("recent", []) if s in vmap)
    eps = list(dict.fromkeys(v["ep"] for v in videos))
    ep_rows = "".join(
        f'<details class="ep"><summary>{E(ep)}<span class="cnt">{sum(1 for v in videos if v["ep"] == ep)} 段</span></summary>'
        f'<div class="vgrid">{"".join(_vid_html(v) for v in videos if v["ep"] == ep)}</div></details>' for ep in eps)
    decided = "".join(_decided_html(d) for d in model["decided"]) or '<p class="empty">還沒有定案紀錄</p>'
    auto = "".join(_auto_html(a) for a in model["auto"]) or '<p class="empty">還沒有自動處理的事</p>'
    gate_items = "".join(f'<li><a class="lnk" href="#{E(x["id"])}">{E(x["title"])}</a></li>' for x in hard[:3])
    gate_html = (f'<details class="fold"><summary><span class="ft">真正擋關 {len(hard)} 條<small>就是上面牌組裡標紅、標橘的卡</small>'
                 f'</span></summary><ol class="notes" style="padding:0 18px 14px 36px;list-style:decimal">{gate_items}</ol></details>'
                 if hard else "")
    soft_html = (f'<details class="fold"><summary><span class="ft">可略過警告 {len(soft)} 件<small>不擋核准・點開才看，也可以順手簽</small>'
                 f'</span></summary>{"".join(card_html(x) for x in soft)}</details>' if soft else "")
    video_block = ""
    if videos:
        video_block = (f'<h2>最近完成的影片<span class="n">每張是 10 幀條・點了才載入影片</span></h2><div class="vrow">{recent}</div>'
                       f'<details class="fold"><summary><span class="ft">全部 {len(videos)} 段<small>依集數・標籤＝待決／你裁示／附註／重跑</small>'
                       f'</span></summary>{ep_rows}</details>')
    raw = "".join(f'<li><a href="{E(l["href"])}" target="_blank" rel="noopener">{E(l["label"])}</a></li>'
                  for l in model.get("raw_links", []))
    key = E(json.dumps([model["project"], model.get("generated_at", "")], ensure_ascii=False))
    hero_state = "hero" if cards else "idle"
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>決策收件匣｜{E(model["project"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@700;900&family=M+PLUS+Rounded+1c:wght@500;700;800&display=swap" rel="stylesheet">
<style>{CSS}{stage_views.CSS}{stage_views.doc_render.CSS}</style></head>
<body data-key="{key}" data-total="{total}">
<div class="sea" aria-hidden="true"><div class="rays"></div><div class="farwhale">{FAR_WHALE}</div><div id="bubbles"></div></div>
<div class="wrap">
<header>
  <div class="brand"><span class="logo">{WHALE_SVG}</span><h1><b>{E(model["project"])}</b>・決策收件匣</h1></div>
  <div class="hero">
    <figure class="mascot">{mascot(hero_state, images, "鯨魚娘")}</figure>
    <div class="say glass"><span class="who">{who}</span>
      <p class="big">{big}</p>
      <p class="sub progress">{progress}</p>
      <p class="sub">{sub}</p></div>
  </div>
  <ol class="stages glass" aria-label="階段進度">{bar}</ol>
  {block}
  {f'<ul class="notes">{notes}</ul>' if notes else ""}
</header>
<main>
<section class="deckzone" aria-label="需要你決定">
  <div class="dhead"><h2>需要你決定</h2><span class="counter" id="counter">{len(hard)} 張・點選項＝簽下並複製回覆</span></div>
  {_deck_html(hard, total, images)}
  <p id="live" class="sr" aria-live="polite" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)"></p>
</section>
{gate_html}
{soft_html}
<p class="hint"><a href="#stages">看各階段成果 ↓</a></p>
<div class="duo">
  <div><h2>你已經決定的<span class="n">{len(model["decided"])} 件</span></h2>
  <details class="fold"><summary><span class="ft">定案與核准紀錄<small>新的在上・點一行看原話</small></span></summary>{decided}</details></div>
  <div><h2>我自動處理了 {len(model["auto"])} 件事<span class="n">依你的授權或規則</span></h2>
  <details class="fold" id="auto"><summary><span class="ft">自動處理紀錄<small>一行一項・點開看來源</small></span></summary>{auto}</details></div>
</div>
{video_block}
{stage_views.render(model.get("stage_views") or [], cur)}
<div class="raw">原始資料（不內嵌，需在專案資料夾內開啟）<ul>{raw}</ul>
<p>產生時間 {E(model["generated_at"])}・h3d inbox</p></div>
</main>
</div>
<div class="signbar glass" role="status">已簽 <b id="k">0</b> 件・擋關 <b id="kh">0／0</b><button class="cta" type="button" data-copyall>複製已簽回覆</button></div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>{JS}{stage_views.JS}</script>
</body></html>'''
