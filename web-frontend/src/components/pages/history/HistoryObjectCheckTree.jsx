import { Tree } from 'antd'

export default function HistoryObjectCheckTree({ treeData, checkedKeys, onCheck }) {
  return (
    <Tree
      checkable
      blockNode
      className="map-tree"
      treeData={treeData}
      checkedKeys={checkedKeys}
      onCheck={(keys) => onCheck(Array.isArray(keys) ? keys : keys.checked)}
    />
  )
}
