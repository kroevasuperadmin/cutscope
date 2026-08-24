Remove the `lucide-react` dependency completely. It ships no TypeScript declarations in this
install and breaks `npm run build` with:
  "Could not find a declaration file for module 'lucide-react'"
Forced reinstalls do not fix it. It is icons — not worth a dependency that can break the build
in the deploy container too.

## DO THIS
1. Find every icon imported from "lucide-react" in components/production-console.tsx (and
   anywhere else it is used).
2. Replace them with small inline SVG React components defined in a new file
   components/icons.tsx. Match the visual weight of lucide: 24x24 viewBox, fill="none",
   stroke="currentColor", strokeWidth={2}, strokeLinecap="round", strokeLinejoin="round",
   and accept className plus standard SVG props so existing styling keeps working.
3. Keep the exact same component names so the call sites barely change.
4. Remove "lucide-react" from package.json dependencies.
5. Give each icon aria-hidden="true" unless it carries meaning on its own.

## VERIFY BEFORE REPORTING
Run `npm run build` and confirm it compiles with no type errors. Report the actual build
output line. Do not report success without running it.
