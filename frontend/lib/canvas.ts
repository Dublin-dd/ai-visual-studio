/**
 * 画布图层状态（纯函数，便于单测）。
 * 图层坐标以画布左上角为原点，单位 px。
 */

export type Layer = {
  id: string;
  assetId: string;
  url: string;
  x: number;
  y: number;
  width: number;
  height: number;
  z: number;
  rotation: number;
};

export type CanvasState = {
  layers: Layer[];
  selectedId: string | null;
  past: Layer[][];
  future: Layer[][];
};

export const BOARD_WIDTH = 1000;
export const BOARD_HEIGHT = 720;
export const MIN_LAYER_SIZE = 40;

export const initialCanvas: CanvasState = {
  layers: [],
  selectedId: null,
  past: [],
  future: [],
};

export type Action =
  | { type: "add"; layer: Omit<Layer, "id" | "z">; id: string }
  | { type: "move"; id: string; x: number; y: number }
  | { type: "resize"; id: string; width: number; height: number }
  | { type: "select"; id: string | null }
  | { type: "remove"; id: string }
  | { type: "front"; id: string }
  | { type: "undo" }
  | { type: "redo" }
  | { type: "replace"; layers: Layer[] }
  | { type: "load"; layers: Layer[] };

const HISTORY_LIMIT = 50;

function pushHistory(state: CanvasState, layers: Layer[]): Pick<CanvasState, "past" | "future"> {
  const past = [...state.past, state.layers].slice(-HISTORY_LIMIT);
  return { past, future: [] };
}

export function clampToBoard(layer: Layer): Layer {
  return {
    ...layer,
    width: Math.max(MIN_LAYER_SIZE, layer.width),
    height: Math.max(MIN_LAYER_SIZE, layer.height),
  };
}

export function nextZ(layers: Layer[]): number {
  return layers.reduce((max, l) => Math.max(max, l.z), 0) + 1;
}

export function canvasReducer(state: CanvasState, action: Action): CanvasState {
  switch (action.type) {
    case "add": {
      const layer: Layer = {
        ...action.layer,
        id: action.id,
        z: nextZ(state.layers),
      };
      const layers = [...state.layers, clampToBoard(layer)];
      return { ...state, layers, selectedId: layer.id, ...pushHistory(state, layers) };
    }
    case "move": {
      const layers = state.layers.map((l) =>
        l.id === action.id ? { ...l, x: action.x, y: action.y } : l
      );
      return { ...state, layers, ...pushHistory(state, layers) };
    }
    case "resize": {
      const layers = state.layers.map((l) =>
        l.id === action.id
          ? clampToBoard({ ...l, width: action.width, height: action.height })
          : l
      );
      return { ...state, layers, ...pushHistory(state, layers) };
    }
    case "select":
      return { ...state, selectedId: action.id };
    case "remove": {
      const layers = state.layers.filter((l) => l.id !== action.id);
      return {
        ...state,
        layers,
        selectedId: state.selectedId === action.id ? null : state.selectedId,
        ...pushHistory(state, layers),
      };
    }
    case "front": {
      const layer = state.layers.find((l) => l.id === action.id);
      if (!layer) return state;
      const layers = state.layers.map((l) =>
        l.id === action.id ? { ...l, z: nextZ(state.layers) } : l
      );
      return { ...state, layers, ...pushHistory(state, layers) };
    }
    case "undo": {
      if (state.past.length === 0) return state;
      const past = [...state.past];
      const previous = past.pop() as Layer[];
      return {
        layers: previous,
        selectedId: null,
        past,
        future: [state.layers, ...state.future].slice(0, HISTORY_LIMIT),
      };
    }
    case "redo": {
      if (state.future.length === 0) return state;
      const [next, ...rest] = state.future;
      return {
        layers: next,
        selectedId: null,
        past: [...state.past, state.layers].slice(-HISTORY_LIMIT),
        future: rest,
      };
    }
    case "replace": {
      return {
        layers: action.layers,
        selectedId: null,
        past: [...state.past, state.layers].slice(-HISTORY_LIMIT),
        future: [],
      };
    }
    case "load": {
      // 从服务端打开画布：不产生撤销记录
      return { layers: action.layers, selectedId: null, past: [], future: [] };
    }
    default:
      return state;
  }
}

/** 服务端图层 → 前端图层 */
export function fromServerLayers(
  items: Array<{
    id: string;
    asset_id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    z: number;
    rotation: number;
    asset?: { url: string } | null;
  }>
): Layer[] {
  return items
    .filter((it) => !!it.asset?.url)
    .map((it) => ({
      id: it.id,
      assetId: it.asset_id,
      url: it.asset!.url,
      x: it.x,
      y: it.y,
      width: it.width,
      height: it.height,
      z: it.z,
      rotation: it.rotation,
    }));
}

/** 前端图层 → 服务端保存结构 */
export function toServerLayers(layers: Layer[]) {
  return layers.map((l) => ({
    asset_id: l.assetId,
    x: Math.round(l.x),
    y: Math.round(l.y),
    width: Math.round(l.width),
    height: Math.round(l.height),
    z: l.z,
    rotation: l.rotation,
  }));
}

/** 新图层的默认摆放：居中，按原图长边缩到不超过 360px */
export function defaultPlacement(
  width: number,
  height: number
): { x: number; y: number; width: number; height: number } {
  const safeW = width > 0 ? width : 512;
  const safeH = height > 0 ? height : 512;
  const scale = Math.min(1, 360 / Math.max(safeW, safeH));
  const w = Math.round(safeW * scale);
  const h = Math.round(safeH * scale);
  return {
    x: Math.round((BOARD_WIDTH - w) / 2),
    y: Math.round((BOARD_HEIGHT - h) / 2),
    width: w,
    height: h,
  };
}
