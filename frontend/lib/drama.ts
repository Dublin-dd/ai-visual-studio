export const SCENES = ["远景", "全景", "中景", "近景", "特写"] as const;
export const CAMERAS = ["固定", "推", "拉", "摇", "移", "跟"] as const;

export type ShotDraft = {
  id?: string;
  scene: string;
  camera: string;
  description: string;
  dialogue: string;
  duration: number;
  character_names: string[];
};

export function emptyShot(index = 1): ShotDraft {
  return {
    scene: "中景",
    camera: "固定",
    description: "",
    dialogue: "",
    duration: 5,
    character_names: [],
  };
}

/** 单行校验：返回错误文案，合法返回 null。 */
export function validateShot(shot: ShotDraft): string | null {
  if (!shot.description.trim()) return "画面描述不能为空";
  if (!Number.isFinite(shot.duration)) return "时长必须是数字";
  if (shot.duration < 2 || shot.duration > 10) return "时长需在 2~10 秒之间";
  if (!SCENES.includes(shot.scene as (typeof SCENES)[number])) return "景别不合法";
  if (!CAMERAS.includes(shot.camera as (typeof CAMERAS)[number])) return "运镜不合法";
  return null;
}

/** 分镜里出现、但角色库没有建档的角色名。 */
export function missingCharacters(shots: ShotDraft[], knownNames: string[]): string[] {
  const known = new Set(knownNames);
  const missing = new Set<string>();
  for (const s of shots) {
    for (const n of s.character_names) {
      if (n && !known.has(n)) missing.add(n);
    }
  }
  return [...missing];
}

/** 解析角色名输入（逗号/顿号/空格分隔）。 */
export function parseNames(input: string): string[] {
  return input
    .split(/[,，、/\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 8);
}

export function toServerShots(shots: ShotDraft[]) {
  return shots.map((s, i) => ({
    index: i + 1,
    scene: s.scene,
    camera: s.camera,
    description: s.description.trim(),
    dialogue: s.dialogue.trim(),
    duration: Math.round(s.duration),
    character_names: s.character_names,
  }));
}

export function totalDuration(shots: ShotDraft[]): number {
  return shots.reduce((sum, s) => sum + (Number.isFinite(s.duration) ? s.duration : 0), 0);
}
