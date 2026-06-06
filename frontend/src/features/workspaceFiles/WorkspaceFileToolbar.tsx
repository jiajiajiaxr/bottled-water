import {
  ArrowLeftOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  FolderAddOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { Button, Input, Select, Space, Statistic, Typography, Upload } from "antd";
import type { UploadProps } from "antd";

const { Title, Text } = Typography;

type Props = {
  query: string;
  source: string;
  sources: Array<{ label: string; value: string }>;
  stats?: { file_count: number; total_size: number };
  loading: boolean;
  checkedCount: number;
  onBack: () => void;
  onQueryChange: (value: string) => void;
  onSourceChange: (value: string) => void;
  onCreateFolder: () => void;
  onMoveSelected: () => void;
  onBulkDelete: () => void;
  onReload: () => void;
  onUploadFile: UploadProps["beforeUpload"];
};

export function WorkspaceFileToolbar({
  query,
  source,
  sources,
  stats,
  loading,
  checkedCount,
  onBack,
  onQueryChange,
  onSourceChange,
  onCreateFolder,
  onMoveSelected,
  onBulkDelete,
  onReload,
  onUploadFile,
}: Props) {
  return (
    <>
      <div className="workspace-files-page-head">
        <Space align="center">
          <Button icon={<ArrowLeftOutlined />} onClick={onBack}>
            返回聊天
          </Button>
          <div>
            <Title level={4}>工作区文件</Title>
            <Text type="secondary">
              统一查看上传、产物、沙箱、导出和项目文件
            </Text>
          </div>
        </Space>
        <Space wrap>
          {stats && (
            <Statistic
              className="workspace-file-stat"
              title="容量"
              value={`${formatBytes(stats.total_size)} / ${stats.file_count} 个文件`}
            />
          )}
          <Button icon={<FolderAddOutlined />} onClick={onCreateFolder}>
            新建文件夹
          </Button>
          <Upload
            multiple
            showUploadList={false}
            beforeUpload={onUploadFile}
          >
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              disabled={loading}
              data-testid="workspace-file-upload"
            >
              上传文件
            </Button>
          </Upload>
          <Button disabled={!checkedCount} onClick={onMoveSelected}>
            移动
          </Button>
          <Button
            danger
            disabled={!checkedCount}
            icon={<DeleteOutlined />}
            onClick={onBulkDelete}
          >
            批量删除
          </Button>
          <Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>
      <Space.Compact block className="workspace-file-toolbar">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索文件名或路径"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
        <Select
          value={source}
          onChange={onSourceChange}
          style={{ width: 160 }}
          options={sources}
        />
      </Space.Compact>
    </>
  );
}

function formatBytes(size: number) {
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size > 1024) return `${Math.ceil(size / 1024)} KB`;
  return `${size} B`;
}
