import { getChatGPTUser } from "./chatgpt-auth";
import WeatherConsole from "./components/weather-console";

export default async function Home() {
  const user = await getChatGPTUser();
  return (
    <WeatherConsole
      operatorName={user?.displayName ?? "Workspace operator"}
      operatorEmail={user?.email ?? null}
    />
  );
}
