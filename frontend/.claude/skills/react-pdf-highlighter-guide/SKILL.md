# React PDF Highlighter Usage Guide

**How to reference this:** When working with `react-pdf-highlighter`, both humans and Claude should reference this guide for the correct patterns and API.

## Overview

`react-pdf-highlighter` is a React component library for annotating PDFs. It provides:
- **Text highlighting**: Select text in a PDF and save highlights
- **Area highlighting**: Hold Alt and drag to create rectangular area highlights with screenshots
- **Annotation system**: Add comments (text + emoji) to highlights
- **Navigation**: Click highlights in a sidebar to scroll to them

## Core Architecture

```
PdfLoader (loads PDF file)
  └─ PdfHighlighter (renders PDF + handles selection)
      ├─ Highlight components (text highlights)
      ├─ AreaHighlight components (rectangular areas)
      └─ Popup/Tip system (show comments)
```

## Quick Start Pattern

```tsx
import { PdfLoader, PdfHighlighter, Highlight, AreaHighlight, Popup, Tip } from 'react-pdf-highlighter'

<PdfLoader url={pdfUrl} beforeLoad={<Spinner />}>
  {(pdfDocument) => (
    <PdfHighlighter
      pdfDocument={pdfDocument}
      highlights={highlights}
      onSelectionFinished={(position, content, hideTipAndSelection, transformSelection) => (
        <Tip
          onOpen={transformSelection}
          onConfirm={(comment) => addHighlight({ content, position, comment })}
        />
      )}
      highlightTransform={(highlight, index, setTip, hideTip, viewportToScaled, screenshot, isScrolledTo) => (
        // Render each highlight
      )}
      scrollRef={(scrollTo) => scrollViewerTo.current = scrollTo}
      enableAreaSelection={(event) => event.altKey}
    />
  )}
</PdfLoader>
```

## Key Components

### 1. **PdfLoader**
Loads a PDF document and exposes it to children.

**Props:**
- `url: string` - URL to the PDF
- `beforeLoad?: ReactNode` - Loading spinner/message

**Usage:**
```tsx
<PdfLoader url="https://arxiv.org/pdf/1708.08021">
  {(pdfDocument) => <PdfHighlighter pdfDocument={pdfDocument} ... />}
</PdfLoader>
```

### 2. **PdfHighlighter** 
Main component that renders the PDF and handles all interaction.

**Key Props:**

| Prop | Type | Description |
|------|------|-------------|
| `pdfDocument` | PDFDocumentProxy | From PdfLoader |
| `highlights` | IHighlight[] | Array of highlight objects |
| `onSelectionFinished` | callback | Fires when user finishes text selection |
| `highlightTransform` | callback | Renders each highlight (called for each item in `highlights`) |
| `scrollRef` | callback | Returns `(highlight: IHighlight) => void` function to scroll to highlight |
| `enableAreaSelection` | (event) => boolean | Return true to enable area selection on mouse drag |
| `onScrollChange` | callback | Fires when user scrolls |

### 3. **Highlight** (Text)
Shows a colored background for text highlights.

```tsx
<Highlight
  isScrolledTo={isScrolledTo}
  position={highlight.position}
  comment={highlight.comment}
/>
```

### 4. **AreaHighlight** (Rectangle)
Shows a draggable rectangle for area highlights.

```tsx
<AreaHighlight
  isScrolledTo={isScrolledTo}
  highlight={highlight}
  onChange={(boundingRect) => {
    updateHighlight(highlight.id, {
      boundingRect: viewportToScaled(boundingRect),
      image: screenshot(boundingRect)
    })
  }}
/>
```

### 5. **Tip** (Comment Input)
Shows a popup when user selects text, lets them add a comment.

```tsx
<Tip
  onOpen={transformSelection}  // For text animation
  onConfirm={(comment) => addHighlight({ content, position, comment })}
/>
```

### 6. **Popup**
Wraps a highlight component and shows content on hover.

```tsx
<Popup
  popupContent={<HighlightPopup comment={highlight.comment} />}
  onMouseOver={(content) => setTip(highlight, () => content)}
  onMouseOut={hideTip}
>
  <Highlight ... />
</Popup>
```

## Data Structures

### IHighlight (Complete highlight object)
```ts
{
  id: string                    // Unique ID
  comment: {
    text: string               // Comment text
    emoji: string              // Emoji (e.g., "🔥")
  }
  content: {
    text?: string              // Selected text (text highlights)
    image?: string             // Base64 screenshot (area highlights)
  }
  position: {
    boundingRect: {
      x1: number               // Left
      y1: number               // Top
      x2: number               // Right
      y2: number               // Bottom
      width: number            // PDF page width
      height: number           // PDF page height
    }
    rects: Array<{             // Multiple rects for wrapped text
      x1, y1, x2, y2, width, height, pageNumber
    }>
    pageNumber: number         // 1-indexed
  }
}
```

### NewHighlight (What you pass to addHighlight)
Same as IHighlight but **without `id`** (assigned by you).

### ScaledPosition (Editable position)
```ts
{
  boundingRect: { x1, y1, x2, y2, width, height }
  rects: Array<{ ... }>
  pageNumber: number
}
```

## Callback Functions

### onSelectionFinished
Called when user finishes selecting text.

```ts
onSelectionFinished = (
  position: ScaledPosition,        // Where on the page
  content: Content,                // What they selected (text)
  hideTipAndSelection: () => void, // Hide the Tip component
  transformSelection: () => void   // Animation helper
) => ReactNode  // Return a Tip component
```

### highlightTransform
Called for **each** highlight in the `highlights` array. Returns JSX to render.

```ts
highlightTransform = (
  highlight: IHighlight,                    // The highlight
  index: number,                            // Array index
  setTip: (highlight, content) => void,     // Show popup
  hideTip: () => void,                      // Hide popup
  viewportToScaled: (rect) => ScaledPosition, // Convert coordinates
  screenshot: (rect) => string,             // Take page screenshot
  isScrolledTo: boolean                     // Is currently scrolled into view
) => ReactNode  // Return JSX (usually Popup wrapping Highlight)
```

### scrollRef
Called once when PdfHighlighter mounts. It passes you a scroll function that you can call later to scroll the PDF to a specific highlight.

**Signature:**
```ts
scrollRef = (scrollTo: (highlight: IHighlight) => void) => void
```

**The scrollTo function:**
- Takes an `IHighlight` object
- Scrolls the PDF viewer to that highlight's position
- Optionally animates/highlights it as "scrolled to"

**Complete Example:**
```tsx
// 1. Create a ref to store the scroll function
const scrollViewerTo = useRef<(h: IHighlight) => void>(() => {})

// 2. Pass scrollRef to PdfHighlighter
<PdfHighlighter 
  scrollRef={(scrollFn) => {
    // PdfHighlighter calls this on mount, passing the scroll function
    scrollViewerTo.current = scrollFn
  }}
  ... 
/>

// 3. Later, call it to scroll to a highlight
const handleClickHighlight = (highlight: IHighlight) => {
  scrollViewerTo.current(highlight)
}
```

**Real-World Use Cases:**

**Scroll from sidebar click:**
```tsx
<Sidebar
  highlights={highlights}
  onHighlightClick={(highlight) => {
    scrollViewerTo.current(highlight)
  }}
/>
```

**Scroll from URL hash (deep linking):**
```tsx
useEffect(() => {
  // Parse highlight ID from URL: #highlight-123
  const id = window.location.hash.slice('#highlight-'.length)
  const highlight = highlights.find(h => h.id === id)
  
  if (highlight && scrollViewerTo.current) {
    scrollViewerTo.current(highlight)
  }
}, [highlights])

// Also handle when hash changes
useEffect(() => {
  const handleHashChange = () => {
    const id = window.location.hash.slice('#highlight-'.length)
    const highlight = highlights.find(h => h.id === id)
    if (highlight) {
      scrollViewerTo.current(highlight)
    }
  }
  
  window.addEventListener('hashchange', handleHashChange)
  return () => window.removeEventListener('hashchange', handleHashChange)
}, [highlights])
```

**Scroll on state change:**
```tsx
const [selectedHighlightId, setSelectedHighlightId] = useState<string | null>(null)

useEffect(() => {
  if (selectedHighlightId) {
    const highlight = highlights.find(h => h.id === selectedHighlightId)
    if (highlight) {
      scrollViewerTo.current(highlight)
    }
  }
}, [selectedHighlightId, highlights])
```

**Important Notes:**
- `scrollRef` is called **once on mount**, not on every render
- The scroll function is safe to call multiple times
- The function is synchronous—scrolling happens immediately
- Calling with a highlight not in the `highlights` array has no effect
- Use `useRef` to persist the function across re-renders (not `useState`)

## Common Patterns

### 1. **Add a highlight** (from selection)
```tsx
onSelectionFinished={(position, content, hide, transform) => (
  <Tip
    onConfirm={(comment) => {
      setHighlights([
        { id: getNextId(), position, content, comment },
        ...highlights
      ])
      hide()
    }}
  />
)}
```

### 2. **Update a highlight** (edit area)
```tsx
onChange={(boundingRect) => {
  setHighlights(highlights.map(h =>
    h.id === highlight.id
      ? { ...h, position: { ...h.position, boundingRect: viewportToScaled(boundingRect) } }
      : h
  ))
}}
```

### 3. **Enable area selection** (Alt+drag)
```tsx
enableAreaSelection={(event) => event.altKey}
```

### 4. **Scroll to highlight from URL hash**
```tsx
useEffect(() => {
  const id = parseIdFromHash()
  const h = highlights.find(x => x.id === id)
  if (h && scrollViewerTo.current) {
    scrollViewerTo.current(h)
  }
}, [])

window.addEventListener('hashchange', () => scrollViewerTo.current(highlight))
```

### 5. **Show comment popup on hover**
```tsx
<Popup
  popupContent={<div>{highlight.comment.emoji} {highlight.comment.text}</div>}
  onMouseOver={(content) => setTip(highlight, () => content)}
  onMouseOut={hideTip}
>
  <Highlight isScrolledTo={isScrolledTo} position={highlight.position} />
</Popup>
```

## Notes for Implementation

- **Coordinates are scaled**: Use `viewportToScaled()` to convert dragged positions
- **Screenshots are Base64**: `screenshot()` returns data URL directly
- **Rects array**: For text that wraps, you get multiple rects (one per line)
- **Enable area selection per-event**: Return true from `enableAreaSelection` to allow drag
- **ID is your responsibility**: Generate unique IDs when adding highlights
- **Comments are required**: `comment: { text, emoji }` on all highlights

## Troubleshooting

**Highlights not showing:** Make sure `highlights` prop is updated and `highlightTransform` is returning JSX.

**Selection doesn't work:** Ensure `onSelectionFinished` is returning a `<Tip>` component.

**Area selection disabled:** Check `enableAreaSelection` returns true on the right event.

**Popup not visible:** Check z-index and that `setTip` is being called correctly.
