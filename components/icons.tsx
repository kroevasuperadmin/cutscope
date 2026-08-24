import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ "aria-hidden": ariaHidden = true, children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden={ariaHidden}
      fill="none"
      height="24"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
      width="24"
      {...props}
    >
      {children}
    </svg>
  );
}

export function Film(props: IconProps) {
  return <Icon {...props}><rect height="20" rx="2.5" width="20" x="2" y="2" /><path d="M7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5" /></Icon>;
}

export function Play(props: IconProps) {
  return <Icon {...props}><polygon points="6 3 20 12 6 21 6 3" /></Icon>;
}

export function Square(props: IconProps) {
  return <Icon {...props}><rect height="12" rx="1.5" width="12" x="6" y="6" /></Icon>;
}

export function RotateCcw(props: IconProps) {
  return <Icon {...props}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></Icon>;
}

export function TriangleAlert(props: IconProps) {
  return <Icon {...props}><path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><path d="M12 9v4M12 17h.01" /></Icon>;
}
