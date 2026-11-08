import { describe, expect, it } from "vitest";
import {
  BOARD_HEIGHT,
  BOARD_WIDTH,
  canvasReducer,
  clampToBoard,
  defaultPlacement,
  fromServerLayers,
  initialCanvas,
  toServerLayers,
  type Action,
  type CanvasState,
} from "./canvas";

function run(state: CanvasState, actions: Action[]): CanvasState {
  return actions.reduce(canvasReducer, state);
}

const addA: Action = {
  type: "add",
  id: "l1",
  layer: { assetId: "a1", url: "/api/files/a1", x: 0, y: 0, width: 100, height: 100, rotation: 0 },
};
const addB: Action = {
  type: "add",
  id: "l2",
  layer: { assetId: "a2", url: "/api/files/a2", x: 50, y: 50, width: 120, height: 80, rotation: 0 },
};

describe("canvasReducer", () => {
  it("加入图层后选中并置顶", () => {
    const s = run(initialCanvas, [addA, addB]);
    expect(s.layers).toHaveLength(2);
    expect(s.selectedId).toBe("l2");
    expect(s.layers[1].z).toBeGreaterThan(s.layers[0].z);
  });

  it("移动图层并支持撤销/重做", () => {
    let s = run(initialCanvas, [addA]);
    const before = s.layers[0].x;
    s = canvasReducer(s, { type: "move", id: "l1", x: 200, y: 120 });
    expect(s.layers[0].x).toBe(200);

    s = canvasReducer(s, { type: "undo" });
    expect(s.layers[0].x).toBe(before);

    s = canvasReducer(s, { type: "redo" });
    expect(s.layers[0].x).toBe(200);
  });

  it("缩放不小于最小尺寸", () => {
    let s = run(initialCanvas, [addA]);
    s = canvasReducer(s, { type: "resize", id: "l1", width: 5, height: 5 });
    expect(s.layers[0].width).toBe(40);
    expect(s.layers[0].height).toBe(40);
  });

  it("删除图层后取消选中", () => {
    let s = run(initialCanvas, [addA]);
    s = canvasReducer(s, { type: "remove", id: "l1" });
    expect(s.layers).toHaveLength(0);
    expect(s.selectedId).toBeNull();
  });

  it("置顶让 z 变大", () => {
    let s = run(initialCanvas, [addA, addB]);
    s = canvasReducer(s, { type: "front", id: "l1" });
    const a = s.layers.find((l) => l.id === "l1")!;
    const b = s.layers.find((l) => l.id === "l2")!;
    expect(a.z).toBeGreaterThan(b.z);
  });

  it("选择空 id 取消选中", () => {
    let s = run(initialCanvas, [addA]);
    s = canvasReducer(s, { type: "select", id: null });
    expect(s.selectedId).toBeNull();
  });

  it("replace 覆盖图层并可撤销", () => {
    let s = run(initialCanvas, [addA]);
    s = canvasReducer(s, {
      type: "replace",
      layers: [
        { id: "x", assetId: "a9", url: "/u", x: 1, y: 2, width: 10, height: 10, z: 1, rotation: 0 },
      ],
    });
    expect(s.layers[0].id).toBe("x");
    s = canvasReducer(s, { type: "undo" });
    expect(s.layers[0].id).toBe("l1");
  });

  it("load 直接覆盖且无历史", () => {
    let s = run(initialCanvas, [addA]);
    s = canvasReducer(s, {
      type: "load",
      layers: [
        { id: "x", assetId: "a9", url: "/u", x: 1, y: 2, width: 10, height: 10, z: 1, rotation: 0 },
      ],
    });
    expect(s.layers[0].id).toBe("x");
    expect(s.past).toHaveLength(0);
    expect(canvasReducer(s, { type: "undo" }).layers[0].id).toBe("x");
  });

  it("空历史时撤销/重做不改状态", () => {
    const s = canvasReducer(initialCanvas, { type: "undo" });
    expect(s.layers).toEqual([]);
    const s2 = canvasReducer(initialCanvas, { type: "redo" });
    expect(s2.layers).toEqual([]);
  });

  it("clampToBoard 保留坐标", () => {
    const l = clampToBoard({
      id: "1",
      assetId: "a",
      url: "u",
      x: -20,
      y: 9999,
      width: 10,
      height: 10,
      z: 1,
      rotation: 0,
    });
    expect(l.x).toBe(-20);
    expect(l.width).toBe(40);
  });
});

describe("服务端结构转换", () => {
  it("fromServerLayers 过滤无素材的行", () => {
    const layers = fromServerLayers([
      {
        id: "1",
        asset_id: "a1",
        x: 1,
        y: 2,
        width: 3,
        height: 4,
        z: 1,
        rotation: 0,
        asset: { url: "/api/files/a1" },
      },
      {
        id: "2",
        asset_id: "a2",
        x: 0,
        y: 0,
        width: 1,
        height: 1,
        z: 2,
        rotation: 0,
        asset: null,
      },
    ]);
    expect(layers).toHaveLength(1);
    expect(layers[0].url).toBe("/api/files/a1");
  });

  it("toServerLayers 取整并改字段名", () => {
    const out = toServerLayers([
      { id: "1", assetId: "a1", url: "/u", x: 1.6, y: 2.2, width: 10.5, height: 20.4, z: 3, rotation: 0 },
    ]);
    expect(out[0]).toEqual({ asset_id: "a1", x: 2, y: 2, width: 11, height: 20, z: 3, rotation: 0 });
  });
});

describe("defaultPlacement", () => {
  it("大图按长边缩到 360 并居中", () => {
    const p = defaultPlacement(1024, 512);
    expect(p.width).toBe(360);
    expect(p.height).toBe(180);
    expect(p.x).toBe(Math.round((BOARD_WIDTH - 360) / 2));
    expect(p.y).toBe(Math.round((BOARD_HEIGHT - 180) / 2));
  });

  it("小图不放大", () => {
    const p = defaultPlacement(100, 100);
    expect(p.width).toBe(100);
    expect(p.height).toBe(100);
  });

  it("尺寸为 0 时用兜底值", () => {
    const p = defaultPlacement(0, 0);
    expect(p.width).toBe(360);
    expect(p.height).toBe(360);
  });
});
