import { ProjectIntake } from "@/components/project-intake";

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectIntake projectId={id} />;
}
