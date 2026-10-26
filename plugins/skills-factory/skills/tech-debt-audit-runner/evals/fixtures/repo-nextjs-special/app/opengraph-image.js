import { ImageResponse } from "next/og";

export const alt = "Fixture";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(<div style={{ fontSize: 96 }}>Fixture</div>, { ...size });
}
