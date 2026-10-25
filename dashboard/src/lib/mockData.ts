import readings from "./mockReadings.json";
import scenarios from "./mockScenarios.json";
import type { Reading } from "@/types";

export const mockReadings = readings as unknown as Reading[];
export const mockScenarios = scenarios as unknown as Record<string, Reading[]>;