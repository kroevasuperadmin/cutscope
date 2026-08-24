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

export function Activity(props: IconProps) {
  return <Icon {...props}><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></Icon>;
}

export function Ban(props: IconProps) {
  return <Icon {...props}><circle cx="12" cy="12" r="10" /><path d="m4.93 4.93 14.14 14.14" /></Icon>;
}

export function CircleStop(props: IconProps) {
  return <Icon {...props}><circle cx="12" cy="12" r="10" /><rect height="6" rx="1" width="6" x="9" y="9" /></Icon>;
}

export function Film(props: IconProps) {
  return <Icon {...props}><rect height="20" rx="2.5" width="20" x="2" y="2" /><path d="M7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5" /></Icon>;
}

export function Gauge(props: IconProps) {
  return <Icon {...props}><path d="m12 14 4-4" /><path d="M3.34 19a10 10 0 1 1 17.32 0" /></Icon>;
}

export function Play(props: IconProps) {
  return <Icon {...props}><polygon points="5 3 19 12 5 21 5 3" /></Icon>;
}

export function Radio(props: IconProps) {
  return <Icon {...props}><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9M7.8 16.2a6 6 0 0 1 0-8.4M19.1 4.9c3.9 3.9 3.9 10.3 0 14.2M16.2 7.8a6 6 0 0 1 0 8.4" /><circle cx="12" cy="12" r="2" /></Icon>;
}

export function RotateCcw(props: IconProps) {
  return <Icon {...props}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></Icon>;
}

export function TriangleAlert(props: IconProps) {
  return <Icon {...props}><path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" /><path d="M12 9v4M12 17h.01" /></Icon>;
}
