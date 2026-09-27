import React from 'react';

interface IconProps extends Omit<React.SVGProps<SVGSVGElement>, 'd'> {
  d?: string | string[];
  size?: number;
}

export function Icon({ d, size = 16, className, style, ...rest }: IconProps) {
  const pathElements = Array.isArray(d)
    ? d.map((p, i) => <path key={i} d={p} />)
    : <path d={d} />;

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      {...rest}
    >
      {pathElements}
    </svg>
  );
}

export const ICN = {
  grid: (p: IconProps) => <Icon {...p} d={["M3 3h7v7H3z", "M14 3h7v7h-7z", "M14 14h7v7h-7z", "M3 14h7v7H3z"]} />,
  camera: (p: IconProps) => <Icon {...p} d={["M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z", "M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"]} />,
  film: (p: IconProps) => <Icon {...p} d={["M3 5h18v14H3z", "M3 9h4M3 15h4M17 9h4M17 15h4M7 5v14M17 5v14"]} />,
  alert: (p: IconProps) => <Icon {...p} d={["M10.3 3.9 1.8 18a1.5 1.5 0 0 0 1.3 2.2h17.8a1.5 1.5 0 0 0 1.3-2.2L13.7 3.9a1.5 1.5 0 0 0-2.6 0Z", "M12 9v4.5", "M12 16.5h.01"]} />,
  map: (p: IconProps) => <Icon {...p} d={["M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z", "M9 4v14M15 6v14"]} />,
  chart: (p: IconProps) => <Icon {...p} d={["M4 20V10", "M11 20V4", "M18 20v-7"]} />,
  history: (p: IconProps) => <Icon {...p} d={["M3 12a9 9 0 1 0 3-6.7", "M3 4v5h5", "M12 8v4l3 2"]} />,
  settings: (p: IconProps) => <Icon {...p} d={["M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z", "M19.4 13a7.7 7.7 0 0 0 .1-2l2-1.5-2-3.4-2.3.9a7.6 7.6 0 0 0-1.7-1L15 3.5h-4l-.4 2.5a7.6 7.6 0 0 0-1.7 1l-2.3-.9-2 3.4L6.5 11a7.7 7.7 0 0 0 0 2l-2 1.5 2 3.4 2.3-.9c.5.4 1 .7 1.7 1l.4 2.5h4l.4-2.5c.6-.3 1.2-.6 1.7-1l2.3.9 2-3.4-2-1.5Z"]} />,
  search: (p: IconProps) => <Icon {...p} d={["M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z", "m21 21-4.3-4.3"]} />,
  bell: (p: IconProps) => <Icon {...p} d={["M6 8a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z", "M10 20a2 2 0 0 0 4 0"]} />,
  layers: (p: IconProps) => <Icon {...p} d={["m12 3 9 5-9 5-9-5 9-5Z", "m3 13 9 5 9-5", "m3 9 9 5 9-5"]} />,
  upload: (p: IconProps) => <Icon {...p} d={["M12 15V4", "m7 8 5-5 5 5", "M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"]} />,
  play: (p: IconProps) => <Icon {...p} d="M7 4.5v15l13-7.5-13-7.5Z" />,
  pause: (p: IconProps) => <Icon {...p} d={["M7 4.5h3.5v15H7z", "M13.5 4.5H17v15h-3.5z"]} />,
  stop: (p: IconProps) => <Icon {...p} d="M5.5 5.5h13v13h-13z" />,
  restart: (p: IconProps) => <Icon {...p} d={["M3 12a9 9 0 1 1 3 6.7", "M3 19v-5h5"]} />,
  chevronRight: (p: IconProps) => <Icon {...p} d="m9 6 6 6-6 6" />,
  chevronDown: (p: IconProps) => <Icon {...p} d="m6 9 6 6 6-6" />,
  x: (p: IconProps) => <Icon {...p} d={["M18 6 6 18", "m6 6 12 12"]} />,
  check: (p: IconProps) => <Icon {...p} d="m5 13 4 4L19 7" />,
  flag: (p: IconProps) => <Icon {...p} d={["M5 21V4", "M5 4h13l-3 4 3 4H5"]} />,
  eye: (p: IconProps) => <Icon {...p} d={["M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"]} />,
  shield: (p: IconProps) => <Icon {...p} d="M12 3 4 6v6c0 5 3.4 7.7 8 9 4.6-1.3 8-4 8-9V6l-8-3Z" />,
  target: (p: IconProps) => <Icon {...p} d={["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z", "M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"]} />,
  wifiOff: (p: IconProps) => <Icon {...p} d={["M2 2l20 20", "M8.5 16.5a5 5 0 0 1 7 0", "M5 13a10 10 0 0 1 3-2.1M19 13a9.9 9.9 0 0 0-2.3-2.9M12 20h.01"]} />,
  wifi: (p: IconProps) => <Icon {...p} d={["M5 13a10 10 0 0 1 14 0", "M8.5 16.5a5 5 0 0 1 7 0", "M12 20h.01"]} />,
  hardDrive: (p: IconProps) => <Icon {...p} d={["M4 13h16l-2-8H6l-2 8Z", "M4 13v6a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-6", "M8 17h.01M12 17h.01"]} />,
  users: (p: IconProps) => <Icon {...p} d={["M17 20v-1.5a3.5 3.5 0 0 0-3.5-3.5h-4A3.5 3.5 0 0 0 6 18.5V20", "M10.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "M17.5 11a2.6 2.6 0 1 0 0-5.2", "M20 20v-1.3a3 3 0 0 0-2-2.8"]} />,
  clock: (p: IconProps) => <Icon {...p} d={["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 7v5l3.5 2"]} />,
  box: (p: IconProps) => <Icon {...p} d={["m3.3 7 8.7 5 8.7-5", "M12 22V12", "M20 7v9.5a1 1 0 0 1-.5.9l-7 4a1 1 0 0 1-1 0l-7-4a1 1 0 0 1-.5-.9V7a1 1 0 0 1 .5-.9l7-4a1 1 0 0 1 1 0l7 4a1 1 0 0 1 .5.9Z"]} />,
  externalLink: (p: IconProps) => <Icon {...p} d={["M14 4h6v6", "m10 14 10-10", "M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h6"]} />,
  note: (p: IconProps) => <Icon {...p} d={["M6 3h9l4 4v14H6z", "M14 3v5h5", "M9 12h6M9 16h6M9 8h2"]} />,
  maximize: (p: IconProps) => <Icon {...p} d={["M8 3H5a2 2 0 0 0-2 2v3", "M16 3h3a2 2 0 0 1 2 2v3", "M21 16v3a2 2 0 0 1-2 2h-3", "M3 16v3a2 2 0 0 0 2 2h3"]} />,
  video: (p: IconProps) => <Icon {...p} d={["M4 6h11a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z", "m16 10 5-3v10l-5-3Z"]} />,
  crosshair: (p: IconProps) => <Icon {...p} d={["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z", "M12 2v3M12 19v3M2 12h3M19 12h3"]} />,
  menu: (p: IconProps) => <Icon {...p} d={["M3 6h18", "M3 12h18", "M3 18h18"]} />,
  cmd: (p: IconProps) => <Icon {...p} d="M7 5a2 2 0 1 1 2 2H5a2 2 0 1 1 2-2v14a2 2 0 1 1-2-2h4a2 2 0 1 1-2 2V5a2 2 0 1 1 2-2h14a2 2 0 1 1-2 2h-4a2 2 0 1 1 2-2" />,
  trend: (p: IconProps) => <Icon {...p} d={["m3 17 6-6 4 4 8-8", "M15 7h6v6"]} />,
  filter: (p: IconProps) => <Icon {...p} d="M4 5h16l-6 8v6l-4 2v-8L4 5Z" />,
  weapon: (p: IconProps) => <Icon {...p} d={["M3 21 12 12", "m17 3 4 4-3 3-4-4", "m14 6 4 4", "M10 15l-3-3 4.5-4.5"]} />,
  door: (p: IconProps) => <Icon {...p} d={["M5 3h11v18H5z", "M20 21H5", "M13 12v.01"]} />,
  package: (p: IconProps) => <Icon {...p} d={["m3.3 7 8.7 5 8.7-5", "M12 22V12", "M20 7v9.5a1 1 0 0 1-.5.9l-7 4a1 1 0 0 1-1 0l-7-4a1 1 0 0 1-.5-.9V7"]} />,
  smoke: (p: IconProps) => <Icon {...p} d={["M4 18c1-2 3-2 4 0s3 2 4 0 3-2 4 0 3 2 4 0", "M6 13c1-2 2.5-3 2-5.5S9 3 11 2"]} />,
  car: (p: IconProps) => <Icon {...p} d={["M5 16h14M5 16a2 2 0 1 1-4 0 2 2 0 0 1 4 0Zm14 0a2 2 0 1 0 4 0 2 2 0 0 0-4 0Z", "M3 16v-3.5L5 8h14l2 4.5V16"]} />,
  send: (p: IconProps) => <Icon {...p} d={["m3 3 18 9-18 9 4.5-9L3 3Z"]} />,
  cpu: (p: IconProps) => <Icon {...p} d={["M6 6h12v12H6z", "M9 9h6v6H9z", "M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"]} />,
  database: (p: IconProps) => <Icon {...p} d={["M12 5c4.4 0 8-1.1 8-2.5S16.4 0 12 0 4 1.1 4 2.5 7.6 5 12 5Z", "M4 2.5V19c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5V2.5", "M4 12c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"]} />,
  link: (p: IconProps) => <Icon {...p} d={["M9 17H7a5 5 0 0 1 0-10h2", "M15 7h2a5 5 0 0 1 0 10h-2", "M8 12h8"]} />,
  ghost: (p: IconProps) => <Icon {...p} d="M12 2a7 7 0 0 0-7 7v11l2.5-2 2 2 2.5-2.5 2.5 2.5 2-2 2.5 2V9a7 7 0 0 0-7-7Z" />,
  radio: (p: IconProps) => <Icon {...p} d={["M12 12a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z", "M8.5 15.5a5 5 0 0 1 0-7", "M15.5 8.5a5 5 0 0 1 0 7", "M5.5 18.5a9 9 0 0 1 0-13", "M18.5 5.5a9 9 0 0 1 0 13"]} />,
};

export function TypeIcon({ type, size, style, className }: { type: string; size?: number; style?: React.CSSProperties; className?: string }) {
  const map: Record<string, (p: IconProps) => JSX.Element> = {
    weapon: ICN.weapon,
    assault: ICN.users,
    intrusion: ICN.door,
    restricted: ICN.shield,
    theft: ICN.package,
    crowd: ICN.users,
    vehicle: ICN.car,
    abandoned: ICN.box,
    loitering: ICN.clock,
    smoke: ICN.smoke,
    tailgating: ICN.door,
    perimeter: ICN.shield,
  };
  const Cmp = map[type.toLowerCase()] || ICN.alert;
  return <Cmp size={size} style={style} className={className} />;
}
