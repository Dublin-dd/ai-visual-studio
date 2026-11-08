"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import StudioNav from "@/components/ui/StudioNav";
import Icon from "@/components/ui/Icon";
import Dialog from "@/components/ui/Dialog";
import { errorMessage } from "@/lib/api";
import {
  chatAgent,
  listAgentMessages,
  listBgm,
  listProductImages,
  listShots,
  uploadBgm,
  uploadProductImage,
  SHOT_STATUS_TEXT,
  type AgentMessage,
  type BgmItem,
  type FinalCardPayload,
  type ProductImage,
  type QuoteCardPayload,
  type ScriptCardPayload,
  type ShotItem,
} from "@/lib/sale";

function isScriptCard(payload: unknown): payload is ScriptCardPayload {
  return (
    !!payload &&
    typeof payload === "object" &&
    Array.isArray((payload as ScriptCardPayload).shots)
  );
}

function isQuoteCard(payload: unknown): payload is QuoteCardPayload {
  return (
    !!payload &&
    typeof payload === "object" &&
    typeof (payload as QuoteCardPayload).total_cost === "number"
  );
}

function isFinalCard(payload: unknown): payload is FinalCardPayload {
  return (
    !!payload &&
    typeof payload === "object" &&
    typeof (payload as FinalCardPayload).total === "number"
  );
}

export default function SalePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [redoIndex, setRedoIndex] = useState<number | null>(null);
  const [workflow, setWorkflow] = useState("idle");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bgm, setBgm] = useState<BgmItem | null>(null);
  const [bgmBusy, setBgmBusy] = useState(false);
  const [previewShot, setPreviewShot] = useState<number | null>(null);
  const [finalUrl, setFinalUrl] = useState<string | null>(null);
  const [shots, setShots] = useState<ShotItem[]>([]);
  const [productImage, setProductImage] = useState<ProductImage | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await listAgentMessages(projectId);
      setMessages(data.messages);
      setWorkflow(data.workflow);
    } catch (e) {
      setError(errorMessage(e));
    }
    try {
      const data = await listBgm(projectId);
      setBgm(data.items[0] ?? null);
    } catch {
      // 背景音乐是可选功能，失败不影响主流程
    }
    try {
      const data = await listShots(projectId);
      setShots(data.items);
      setFinalUrl(data.final_url);
    } catch {
      // 镜头列表未就绪时忽略
    }
    try {
      const data = await listProductImages(projectId);
      setProductImage(data.items[0] ?? null);
    } catch {
      // 商品图列表未就绪时忽略
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const sendLock = useRef(false);

  const send = async (text: string, cardId?: string, finalAssetId?: string) => {
    if (!text.trim() || sendLock.current) return;
    sendLock.current = true;
    setBusy(true);
    setError(null);
    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: "user", kind: "text", content: text, payload: {}, created_at: null },
    ]);
    setInput("");
    try {
      const { reply, message_id, workflow: nextWorkflow } = await chatAgent(projectId, text, cardId, finalAssetId);
      setWorkflow(nextWorkflow);
      setMessages((prev) => [
        ...prev,
        {
          id: message_id,
          role: "assistant",
          kind: reply.kind,
          content: reply.content,
          payload: reply.payload,
          created_at: null,
        },
      ]);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      sendLock.current = false;
      setBusy(false);
      try {
        const data = await listShots(projectId);
        setShots(data.items);
      setFinalUrl(data.final_url);
      } catch {
        // 忽略刷新失败
      }
    }
  };

  const onProductPick = async (file: File | undefined) => {
    if (!file || uploading) return;
    if (!file.type.startsWith("image/")) {
      setError("请上传图片文件（JPG / PNG / WEBP）");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const img = await uploadProductImage(projectId, file);
      setProductImage(img);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setUploading(false);
      setDragging(false);
    }
  };

  const onBgmPick = async (file: File | undefined) => {
    if (!file || bgmBusy) return;
    setBgmBusy(true);
    setError(null);
    try {
      const item = await uploadBgm(projectId, file);
      setBgm(item);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBgmBusy(false);
    }
  };

  return (
    <main className="studio">
      <StudioNav active="sale" />
      <Dialog open={redoIndex !== null} onClose={() => setRedoIndex(null)} title="重做镜头">
        <p>将重新生成镜头 {redoIndex}，预计产生约 ¥1 视频费用，并重新配音合成。配音可能另行计费。</p>
        <div className="script-actions"><button className="btn" onClick={() => setRedoIndex(null)}>取消</button><button className="btn btn-primary" disabled={busy} onClick={() => { const index = redoIndex; setRedoIndex(null); if (index !== null) void send(`重做镜头 ${index}`); }}>确认重做</button></div>
      </Dialog>
      <div className="sale-layout">
        <header className="sale-header">
          <Link href="/sale" className="btn">
            <Icon name="back" size={16} />
            返回
          </Link>
          <h1>带货视频</h1>
          <span className="chip">{({idle:"待开始", awaiting_product:"待补充商品信息", script_draft:"待确认脚本", awaiting_product_image:"待确认商品图", quote_draft:"待确认报价", generating:"镜头生成中", composing:"成片合成中", final_review:"待确认成片", done:"已完成"} as Record<string,string>)[workflow] || "处理中"}</span>
          <button className="btn" onClick={() => void load()} disabled={busy}>
            <Icon name="refresh" size={14} />
            刷新进度
          </button>
          <label className="bgm-pick">
            <Icon name="upload" size={14} />
            {bgmBusy ? "上传中…" : bgm ? `BGM：${bgm.filename}` : "加背景音乐（可选）"}
            <input
              type="file"
              accept="audio/mpeg,audio/wav,audio/mp4,.mp3,.wav,.m4a"
              onChange={(e) => void onBgmPick(e.target.files?.[0])}
              hidden
            />
          </label>
        </header>

        <div className="sale-workspace-grid">
        <section className="sale-production" aria-label="制作工作区">
          <div className="sale-section-heading"><div><span className="eyebrow">PRODUCTION SPACE</span><h2>让商品，成为主角。</h2></div><span className="chip">{shots.filter(shot => shot.status === "done").length} / {shots.length} 镜头就绪</span></div>
        {finalUrl && (workflow === "final_review" || workflow === "done") && (
          <section aria-label="当前成片">
            <FinalCard payload={{total: shots.length, video_url: finalUrl, confirmed: workflow === "done"}}
              onConfirm={() => { if (!busy) void send("确认", undefined, finalUrl.split("/").pop()); }} disabled={busy} />
          </section>
        )}
        {shots.length > 0 && (
          <section className="shot-panel" aria-label="镜头列表">
            {shots.map((s) => (
              <div key={s.index} className={`shot-chip ${s.status}`}>
                <span className="shot-chip-title">
                  镜头 {s.index}
                  <em>{SHOT_STATUS_TEXT[s.status]}</em>
                </span>
                <span className="shot-chip-meta">
                  {s.scene}/{s.camera}
                </span>
                {s.status === "done" && s.video_url && (
                  <button type="button" onClick={() => setPreviewShot(s.index)} className="shot-chip-link" aria-pressed={previewShot === s.index}>预览镜头</button>
                )}
                {(s.status === "done" || s.status === "failed") && (
                  <button
                    className="shot-chip-redo"
                    onClick={() => setRedoIndex(s.index)}
                    disabled={busy}
                    title={`重新生成第 ${s.index} 个镜头（约 ¥1）`}
                  >
                    <Icon name="refresh" size={12} />
                    重做
                  </button>
                )}
                {s.status === "failed" && s.error && (
                  <span className="shot-chip-error">{s.error}</span>
                )}
              </div>
            ))}
          </section>
        )}

        <div
          className={`product-bar${dragging ? " dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            void onProductPick(e.dataTransfer.files?.[0]);
          }}
        >
          {productImage ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element -- 本地文件接口 */}
              <img className="product-thumb" src={productImage.url} alt="商品图预览" />
              <div className="product-info">
                <strong>商品图已就绪</strong>
                <span>
                  {productImage.width}×{productImage.height} · 将作为每个镜头的首帧
                </span>
              </div>
              <button className="btn btn-primary" onClick={() => void send("图传好了")} disabled={busy}>
                用这张出片
              </button>
              <label className="btn">
                换一张
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(e) => void onProductPick(e.target.files?.[0])}
                  hidden
                />
              </label>
            </>
          ) : (
            <>
              <Icon name="upload" size={16} />
              <span className="product-hint">
                {uploading ? "正在上传…" : "把商品图拖到这里，或"}
              </span>
              <label className="btn btn-primary">
                选择商品图
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(e) => void onProductPick(e.target.files?.[0])}
                  hidden
                />
              </label>
              <span className="product-sub">JPG / PNG / WEBP，不超过 20MB</span>
            </>
          )}
        </div>

        {previewShot !== null && shots.find(shot => shot.index === previewShot)?.video_url && <section className="sale-clip-preview"><div className="script-card-head"><h3>镜头 {previewShot} · 片段预览</h3><button className="btn" onClick={() => setPreviewShot(null)}>收起</button></div><video key={shots.find(shot => shot.index === previewShot)?.video_url} src={shots.find(shot => shot.index === previewShot)?.video_url || undefined} controls playsInline preload="metadata" /></section>}
        {!finalUrl && previewShot === null && <div className="sale-production-empty"><Icon name="sparkle" size={28} /><h3>{shots.length ? "每一个镜头，都在这里成形。" : "从一张商品图开始"}</h3><p>{shots.length ? "片段就绪后点击预览，全部完成后在这里查看成片。" : "上传商品图，在右侧告诉 AI 商品、卖点和想要的风格。"}</p></div>}
        </section>
        <section className="sale-conversation" aria-label="创作对话"><div className="sale-conversation-heading"><Icon name="sparkle" size={16} /><h2>创作助手</h2><span>一起完成下一步</span></div>
        <div className="sale-chat">
          {messages.length === 0 && !busy && (
            <div className="sale-empty">
              <Icon name="sparkle" size={32} />
              <h3>说一句话，开始做带货视频</h3>
              <p>例如：「帮我做带货视频」——之后上传商品图、告诉 AI 商品和卖点即可。</p>
            </div>
          )}
          {messages.map((m) => <fieldset key={m.id} className="message-card-group" disabled={busy || m.id !== messages.filter(item => item.role === "assistant").at(-1)?.id}> {
            m.role === "user" ? (
              <div key={m.id} className="chat-row user">
                <div className="chat-bubble user">{m.content}</div>
              </div>
            ) : m.kind === "script_card" && isScriptCard(m.payload) ? (
              <ScriptCard
                key={m.id}
                payload={m.payload}
                onConfirm={() => void send("确认", m.id)}
                onRedo={() => void send("重做", m.id)}
              />
            ) : m.kind === "quote_card" && isQuoteCard(m.payload) ? (
              <QuoteCard
                key={m.id}
                payload={m.payload}
                onConfirm={() => void send("确认", m.id)}
                onRedo={() => void send("重做", m.id)}
              />
            ) : m.kind === "final_card" && isFinalCard(m.payload) ? (
              <FinalCard key={m.id} payload={m.payload} onConfirm={() => void send("确认", m.id)} />
            ) : (
              <div key={m.id} className="chat-row assistant">
                <div className="chat-bubble assistant">{m.content}</div>
              </div>
            )
          }</fieldset>)}
          {busy && (
            <div className="chat-row assistant">
              <div className="chat-bubble assistant">正在处理指令，请稍候…</div>
            </div>
          )}
          {error && (
            <div role="alert" className="studio-notice error">
              <Icon name="warning" />
              <span>{error}</span>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <form
          className="sale-input"
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="例如：商品是保温杯，卖点是保温12小时、不漏水"
            disabled={busy}
            aria-label="给 Agent 发消息"
          />
          <button className="btn btn-primary" disabled={busy || !input.trim()}>
            发送
            <Icon name="arrow" size={16} />
          </button>
        </form>
        <p className="sale-cost-note">脚本、出片与成片由你确认，付费操作执行前会提示。</p>
        </section></div>
      </div>
    </main>
  );
}

function ScriptCard({
  payload,
  onConfirm,
  onRedo,
}: {
  payload: ScriptCardPayload;
  onConfirm: () => void;
  onRedo: () => void;
}) {
  return (
    <div className="script-card">
      <div className="script-card-head">
        <span className="eyebrow">带货脚本 · {payload.product_name}</span>
        {payload.audience && <span className="chip">{payload.audience}</span>}
      </div>
      {payload.hook && <p className="script-hook">「{payload.hook}」</p>}
      {payload.selling_points.length > 0 && (
        <div className="selling-points">
          {payload.selling_points.map((p, i) => (
            <span key={i} className="chip">
              {p}
            </span>
          ))}
        </div>
      )}
      <p className="script-text">{payload.script_text}</p>
      <div className="shot-list">
        {payload.shots.map((s) => (
          <div key={s.index} className="shot-row">
            <span className="shot-meta">
              镜头{s.index} · {s.scene}/{s.camera} · {s.duration}s
            </span>
            <p className="shot-desc">画面：{s.description}</p>
            <p className="shot-voice">口播：{s.voiceover}</p>
          </div>
        ))}
      </div>
      <div className="script-actions">
        <button className="btn btn-primary" onClick={onConfirm}>
          <Icon name="check" size={16} />
          确认脚本
        </button>
        <button className="btn" onClick={onRedo}>
          <Icon name="refresh" size={16} />
          重做
        </button>
      </div>
    </div>
  );
}

function QuoteCard({
  payload,
  onConfirm,
  onRedo,
}: {
  payload: QuoteCardPayload;
  onConfirm: () => void;
  onRedo: () => void;
}) {
  return (
    <div className="script-card">
      <div className="script-card-head">
        <span className="eyebrow">出片报价</span>
      </div>
      <div className="quote-row">
        <span className="chip">{payload.shot_count} 个镜头</span>
        <span className="chip">¥{payload.unit_cost}/段</span>
      </div>
      <p className="quote-total">合计约 ¥{payload.total_cost}</p>
      <p className="shot-voice">每个镜头约 6 分钟，会逐段生成。确认后开始，产生费用。</p>
      <div className="script-actions">
        <button className="btn btn-primary" onClick={onConfirm}>
          <Icon name="check" size={16} />
          确认出片
        </button>
        <button className="btn" onClick={onRedo}>
          <Icon name="refresh" size={16} />
          重做脚本
        </button>
      </div>
    </div>
  );
}

function FinalCard({ payload, onConfirm, disabled = false }: { payload: FinalCardPayload; onConfirm: () => void; disabled?: boolean }) {
  return (
    <div className="script-card">
      <div className="script-card-head">
        <span className="eyebrow">{payload.confirmed ? "成片 · 已确认" : "成片 · 待预览确认"}</span>
        <span className="chip">{payload.total} 个镜头</span>
      </div>
      {payload.video_url ? (
        <>
          <video
            className="final-video"
            src={payload.video_url}
            controls
            playsInline
            preload="metadata"
          />
          <div className="script-actions">
            {payload.confirmed === false && <button className="btn btn-primary" disabled={disabled} onClick={onConfirm}>确认成片</button>}
            <a className="btn" href={payload.video_url} download>
              <Icon name="download" size={16} />
              下载成片
            </a>
          </div>
        </>
      ) : (
        <p className="script-hook">✅ 共 {payload.total} 段片段已生成</p>
      )}
    </div>
  );
}
