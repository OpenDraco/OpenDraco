/** Central icon catalogue — semantic name → Heroicons SVG. Use `ICON`
 * in `provideIcons(...)`, `name="bin"` in templates, and `IconName`
 * for typed inputs. */
import {
  // Action / verb glyphs
  heroTrash,
  heroBookmarkSquare,        // save
  heroPencilSquare,          // rename
  heroArrowPath,             // refresh / restore
  heroArrowsRightLeft,       // re-layout
  heroArrowUpRight,          // add-edge
  heroArrowUturnLeft,        // undo
  heroArrowUturnRight,       // redo
  heroArrowDownTray,         // download
  heroFolder,                // open path / reveal-in-explorer
  heroFolderOpen,            // open-state folder
  heroEye,                   // view / inspect
  heroPlay,                  // run / start
  // Status / state glyphs
  heroCheck,
  heroXMark,
  heroXCircle,               // failure / dismiss in a circular badge
  heroExclamationTriangle,
  heroStop,                  // outline square — used for checkbox unchecked
  heroStopCircle,
  heroCheckCircle,           // checkbox checked / success badge
  // Navigation / disclosure glyphs
  heroChevronRight,
  heroChevronDown,
  // Domain-specific glyphs
  heroClock,                 // version-history toolbar button + hourglass-ish status
  heroSquaresPlus,           // graph view-mode toggle
  heroPlusCircle,            // diff add helper
  heroMinusCircle,           // diff remove helper
} from '@ng-icons/heroicons/outline';

export const ICON = {
  // ─── Action / verb glyphs ───────────────────────────────────────
  bin: heroTrash,
  save: heroBookmarkSquare,
  pencil: heroPencilSquare,
  refresh: heroArrowPath,
  shuffle: heroArrowsRightLeft,
  arrowUpRight: heroArrowUpRight,
  undo: heroArrowUturnLeft,
  redo: heroArrowUturnRight,
  download: heroArrowDownTray,
  folder: heroFolder,
  folderOpen: heroFolderOpen,
  eye: heroEye,
  play: heroPlay,

  // ─── Status / state glyphs ──────────────────────────────────────
  check: heroCheck,
  cross: heroXMark,
  crossCircle: heroXCircle,
  warn: heroExclamationTriangle,
  hourglass: heroClock,
  stop: heroStopCircle,
  /** Heroicons has no `heroSquare`; `heroStop` outline is the same shape. */
  square: heroStop,
  squareChecked: heroCheckCircle,

  // ─── Navigation / disclosure glyphs ─────────────────────────────
  chevronRight: heroChevronRight,
  chevronDown: heroChevronDown,
  close: heroXMark,

  // ─── Domain-specific glyphs ─────────────────────────────────────
  clock: heroClock,
  graph: heroSquaresPlus,
  diffAdd: heroPlusCircle,
  diffRm: heroMinusCircle,
} as const;

export type IconName = keyof typeof ICON;
